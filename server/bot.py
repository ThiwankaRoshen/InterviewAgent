import os
import tempfile
import uuid
import wave

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService 
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

# from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from langsmith_processor import setup_langsmith_tracing
load_dotenv(override=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session.

    Args:
        transport: The transport for this session, built by ``create_transport``
            (or by hand for the dial-out/SIP production flows).
        runner_args: Runner session arguments. Carries the request ``body``
            (e.g. dial-out settings, SIP call details) and ``session_id``; the
            standard web/telephony pipelines don't need it.
    """
    logger.info("Starting bot")
    
    conversation_id = str(uuid.uuid4())
    # Configure OpenTelemetry export to LangSmith and register the span processor.
    # This reads OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS from your
    # environment and returns the processor so you can register a recording later.
    tracing_processor = setup_langsmith_tracing()

    # Record the whole conversation as a stereo WAV (user left / bot right) and
    # register the path so the LangSmith root span gets the audio attached.
    # recording_path = os.path.join(tempfile.gettempdir(), f"langgym-{conversation_id}.wav")
    # audiobuffer = AudioBufferProcessor(num_channels=2)
    # tracing_processor.register_recording(conversation_id, recording_path)

    stt = AssemblyAISTTService(
        api_key=os.getenv("ASSEMBLYAI_API_KEY")
    )
    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        voice=os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en"),
    )
    llm = OpenAILLMService(
        api_key=os.getenv("GITHUB_TOKEN"),
        base_url="https://models.github.ai/inference",
        model="openai/gpt-4o-mini",
    )

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant in a voice conversation. "
                    "Your responses will be spoken aloud, so avoid emojis, "
                    "bullet points, or other formatting that can't be spoken. "
                    "Respond to what the user said in a creative, helpful, "
                    "and brief way."
                ),
            }
        ]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    # Pipeline - assembled from reusable components
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            # audiobuffer,         # tap user + bot audio for the recording
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True, 
            enable_usage_metrics=True
        ),
        # idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        enable_tracing=True,             # emit conversation/turn/stt/llm/tts spans
        enable_turn_tracking=True,
        conversation_id=conversation_id,  # root span id == the LangSmith thread
    )

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        
        # await audiobuffer.start_recording()
        # Speak a fixed greeting (no LLM call) and record it as the assistant's
        # first turn, so the first real user message has something to follow.
        
        context.add_message(
            {"role": "developer", "content": "Start by concisely introducing yourself."}
        )
        await worker.queue_frames([LLMRunFrame()])

    # @audiobuffer.event_handler("on_audio_data")
    # async def on_audio_data(buffer, audio, sample_rate, num_channels):  # noqa: ANN001
    #     # Fires once on stop_recording(): write the merged stereo WAV to the path
    #     # the tracing processor reads and attaches to the conversation span.
    #     with wave.open(recording_path, "wb") as wf:
    #         wf.setnchannels(num_channels)
    #         wf.setsampwidth(2)  # PCM16
    #         wf.setframerate(sample_rate)
    #         wf.writeframes(audio)
    #     logger.info(f"Saved conversation recording: {recording_path}")
        
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        # Stop first so the WAV is written before the conversation span ends and
        # the tracing processor reads it.
        # await audiobuffer.stop_recording()
        
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    transport_params = { 
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
