import os
import tempfile
import uuid
import wave
import asyncio

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
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from langsmith_processor import setup_langsmith_tracing
from mock_bot_utils import MockStage, MOCK_QUESTIONS, ActiveInterviewState, make_interview_tools, generate_system_prompt_mock
load_dotenv(override=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session."""
    logger.info("Starting bot")

    conversation_id = str(uuid.uuid4())

    tracing_processor = setup_langsmith_tracing(
        thread_id_provider=lambda: conversation_id,
    )

    recording_path = os.path.join(tempfile.gettempdir(), f"recording_{conversation_id}.wav")
    audio_buffer = AudioBufferProcessor(num_channels=2)
    tracing_processor.register_recording(conversation_id, recording_path)

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(processor, audio, sample_rate, num_channels):
        with wave.open(recording_path, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio)

    stt = AssemblyAISTTService(
        api_key=os.getenv("ASSEMBLYAI_API_KEY")
    )
    tts = DeepgramTTSService(
        settings=DeepgramTTSService.Settings(
            voice=os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en"),
        ),
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )
    llm = OpenAILLMService(
        settings=OpenAILLMService.Settings(
            model=os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini"),
        ),
        api_key=os.getenv("GITHUB_TOKEN"),
        base_url="https://models.github.ai/inference",
    )

    stage = MockStage()  # hardcoded fixture instead of a DB fetch
    active_session = ActiveInterviewState(practice_stage_id=999, questions=MOCK_QUESTIONS)
    tools_schema, handlers = make_interview_tools(active_session)
    system_prompt = generate_system_prompt_mock(stage)

    for name, handler in handlers.items():
        llm.register_function(name, handler)

    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=tools_schema,
    )
    
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            audio_buffer,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        enable_tracing=True,
        enable_turn_tracking=True,
        conversation_id=conversation_id,
    )

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message(
            {"role": "developer", "content": "Start by concisely introducing yourself."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        await audio_buffer.start_recording()

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await audio_buffer.stop_recording()
        await worker.cancel()
        await asyncio.sleep(5)  # Simple delay for trace export

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