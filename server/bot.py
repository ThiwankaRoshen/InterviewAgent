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

from langsmith_processor import setup_langsmith_tracing

load_dotenv(override=True)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session."""
    logger.info("Starting bot")

    conversation_id = str(uuid.uuid4())

    tracing_processor = setup_langsmith_tracing()

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

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
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

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
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