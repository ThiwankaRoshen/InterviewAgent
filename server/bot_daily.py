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
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService 
from pipecat.workers.runner import WorkerRunner

# ═══════════════════════════════════════════════════════════════
# CHANGED: Import Daily transport instead of SmallWebRTC
# ═══════════════════════════════════════════════════════════════
from pipecat.transports.daily.transport import DailyTransport, DailyParams

from sqlalchemy.ext.asyncio import AsyncSession

from langsmith_processor import setup_langsmith_tracing
from bot_utils import (
    close_and_persist_interview_stage,
    initialize_active_session_state,
    make_interview_tools,
    generate_system_prompt,
)
from database import AsyncSessionLocal

load_dotenv(override=True)


async def run_bot(
    transport: DailyTransport,  # Type hint updated
    stage_id: int, 
    practice_session_id: int, 
    db: AsyncSession
) -> None:
    """Run the voice bot for this session."""
    logger.info("Starting bot")

    conversation_id = str(uuid.uuid4())

    tracing_processor = setup_langsmith_tracing(
        thread_id_provider=lambda: conversation_id,
    )

    recording_path = os.path.join(
        tempfile.gettempdir(), f"recording_{conversation_id}.wav"
    )
    audio_buffer = AudioBufferProcessor(num_channels=2)
    tracing_processor.register_recording(conversation_id, recording_path)

    @audio_buffer.event_handler("on_audio_data")
    async def on_audio_data(processor, audio, sample_rate, num_channels):
        with wave.open(recording_path, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio)

    # ═══════════════════════════════════════════════════════════════
    # SERVICES - Unchanged
    # ═══════════════════════════════════════════════════════════════
    stt = AssemblyAISTTService(api_key=os.getenv("ASSEMBLYAI_API_KEY"))
    
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
    
    # ═══════════════════════════════════════════════════════════════
    # DATABASE - Unchanged
    # ═══════════════════════════════════════════════════════════════
    system_prompt = await generate_system_prompt(stage_id, db)
    active_session = await initialize_active_session_state(
        stage_id, practice_session_id, db
    )
    tools_schema, handlers = make_interview_tools(active_session)

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

    # ═══════════════════════════════════════════════════════════════
    # PIPELINE - Unchanged (transport.input/output work the same)
    # ═══════════════════════════════════════════════════════════════
    pipeline = Pipeline(
        [
            transport.input(),      # Audio FROM user (via Daily)
            stt,                     # Speech to text
            user_aggregator,         # Build LLM context
            llm,                     # LLM processing
            tts,                     # Text to speech
            audio_buffer,            # Record conversation
            transport.output(),      # Audio TO user (via Daily)
            assistant_aggregator,    # Track assistant responses
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

    # ═══════════════════════════════════════════════════════════════
    # EVENT HANDLERS - Updated for Daily's event names
    # ═══════════════════════════════════════════════════════════════
    
    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        """Bot is ready and waiting in the room."""
        logger.info("Bot ready, waiting for user to join")
        # Don't start conversation until user joins

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        """User joined the Daily room - start the conversation."""
        logger.info(f"Participant joined: {participant.get('user_name', 'unknown')}")
        await audio_buffer.start_recording()
        
        # Now start the conversation
        context.add_message(
            {"role": "developer", "content": "Start by concisely introducing yourself."}
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant):
        """User left the Daily room."""
        logger.info(f"Participant left: {participant.get('user_name', 'unknown')}")
        await audio_buffer.stop_recording()
        await worker.cancel()
        
        # Wait a bit for any pending traces to export
        await asyncio.sleep(5)
        
        # Persist interview data
        await close_and_persist_interview_stage(active_session, db)

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        """Handle Daily transport errors."""
        logger.error(f"Daily transport error: {error}")

    # ═══════════════════════════════════════════════════════════════
    # RUN - Unchanged
    # ═══════════════════════════════════════════════════════════════
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()


# ═══════════════════════════════════════════════════════════════
# CHANGED: New entry point for Daily - no webrtc_connection needed
# ═══════════════════════════════════════════════════════════════
async def run_bot_entrypoint(
    room_url: str,
    token: str,
    stage_id: int, 
    practice_session_id: int
):
    """
    Entry point called from FastAPI.
    
    Args:
        room_url: The Daily.co room URL (e.g., "https://your-domain.daily.co/abc123")
        stage_id: Interview stage ID
        practice_session_id: Practice stage ID
    """
    # ═══════════════════════════════════════════════════════════════
    # CHANGED: Create DailyTransport instead of SmallWebRTCTransport
    # ═══════════════════════════════════════════════════════════════
    transport = DailyTransport(
        room_url=room_url,
        token=token,  
        params=DailyParams(
            api_key=os.getenv("DAILY_API_KEY"),
            audio_in_enabled=True,      # Hear the user
            audio_out_enabled=True,     # Speak to the user
            camera_out_enabled=False,   # No video from bot
            vad_analyzer=SileroVADAnalyzer(),
            # Optional: Configure audio quality
            # audio_out_sample_rate=16000,
            # audio_out_channels=1,
        ),
    )

    # Fresh DB session that lives as long as the call
    async with AsyncSessionLocal() as db:
        try:
            await run_bot(transport, stage_id, practice_session_id, db)
        except asyncio.CancelledError:
            logger.info("Bot task was cancelled")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
        finally:
            # Cleanup Daily connection
            await transport.cleanup()
            logger.info("Bot cleaned up")


