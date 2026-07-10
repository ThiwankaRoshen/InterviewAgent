import os
import tempfile
import uuid
import wave
import asyncio

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy, TranscriptionUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
    LLMAssistantAggregatorParams
)  
from pipecat.utils.context.llm_context_summarization import (
    LLMAutoContextSummarizationConfig,
    LLMContextSummaryConfig,
)

from pipecat.flows import FlowManager

from bot_flow import (
    create_greeting_node,
    initialize_active_session_state,
    close_and_persist_interview_stage,
)

from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService 
# from pipecat.services.nvidia.llm import NvidiaLLMService
from pipecat.services.google.llm import GoogleLLMService
# from pipecat.services.groq.llm import GroqLLMService
# from pipecat.services.openrouter.llm import OpenRouterLLMService

from pipecat.workers.runner import WorkerRunner

from pipecat.transports.daily.transport import DailyTransport, DailyParams

from sqlalchemy.ext.asyncio import AsyncSession
# from langsmith_processor import setup_langsmith_tracing
from langsmith.integrations.pipecat import configure_pipecat, set_thread_id
from database import AsyncSessionLocal
import contextlib

load_dotenv(override=True)


async def run_bot(
    transport: DailyTransport,  # Type hint updated
    stage_id: int, 
    practice_attempt_id: int, 
    db: AsyncSession,   
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run the voice bot for this session."""
    logger.info("Starting bot")
    stop_event = stop_event or asyncio.Event()


    conversation_id = str(uuid.uuid4())

    # tracing_processor = setup_langsmith_tracing(
    #     thread_id_provider=lambda: conversation_id,
    # )

    # recording_path = os.path.join(
    #     tempfile.gettempdir(), f"recording_{conversation_id}.wav"
    # )
    # audio_buffer = AudioBufferProcessor(num_channels=2)
    # tracing_processor.register_recording(conversation_id, recording_path)

    # @audio_buffer.event_handler("on_audio_data")
    # async def on_audio_data(processor, audio, sample_rate, num_channels):
    #     with wave.open(recording_path, "wb") as wf:
    #         wf.setnchannels(num_channels)
    #         wf.setsampwidth(2)
    #         wf.setframerate(sample_rate)
    #         wf.writeframes(audio)
    span_processor = configure_pipecat()
    set_thread_id(conversation_id)

    audiobuffer = AudioBufferProcessor(num_channels=2, buffer_size=32_000)
    span_processor.attach_audio_buffer(audiobuffer, conversation_id=conversation_id)
    # ═══════════════════════════════════════════════════════════════
    # SERVICES - Unchanged
    # ═══════════════════════════════════════════════════════════════
    stt = AssemblyAISTTService(
        api_key=os.getenv("ASSEMBLYAI_API_KEY"),
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",   # or "u3-rt-pro" — supports tier-1 language steering
            language="en",               # locks/steers transcription to English
            language_detection=False,    # mutually exclusive with language — make sure it's off
            format_turns=True,
        ),
    )
    
    tts = DeepgramTTSService(
        settings=DeepgramTTSService.Settings(
            voice=os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en"),
        ),
        api_key=os.getenv("DEEPGRAM_API_KEY"),
    )
    
    # llm = OpenAILLMService(
    #     settings=OpenAILLMService.Settings(
    #         model=os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini"),
    #     ),
    #     api_key=os.getenv("GITHUB_TOKEN"),
    #     base_url="https://models.github.ai/inference",
    # ) 
    
    # llm = NvidiaLLMService(
    #     api_key=os.getenv("NVIDIA_API_KEY"),
    #     settings=NvidiaLLMService.Settings(
    #         model="nvidia/nemotron-3-nano-30b-a3b",
    #     ), 
    #     # base_url defaults to https://integrate.api.nvidia.com/v1
    # )
    

    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            model="gemini-3.5-flash",  # good balance of speed/cost for voice
        ),
    )
    

    # llm = GroqLLMService(
    #     api_key=os.getenv("GROQ_API_KEY"),
    #     settings=GroqLLMService.Settings(
    #         model="openai/gpt-oss-120b",
    #         # model="llama-3.3-70b-versatile",
    #     ),
    # )   

    # llm = OpenRouterLLMService(
    #     api_key=os.getenv("OPENROUTER_API_KEY"),
    #     settings=OpenRouterLLMService.Settings(
    #         model="openrouter/free",
    #     ),
    # )
    
    active_session = await initialize_active_session_state(
        stage_id, practice_attempt_id, db
    )
    
    # ═══════════════════════════════════════════════════════════════
    # TURN TAKING
    # ═══════════════════════════════════════════════════════════════
    vad_analyzer = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.7,
            start_secs=0.2,   # default; lower to ~0.15 only if short "yes"/"no" get missed
            stop_secs=0.2,    # keep short — Smart Turn (below) handles the "are they really done" call
            min_volume=0.6,
        )
    )

    turn_analyzer = LocalSmartTurnAnalyzerV3(
        params=SmartTurnParams(
            stop_secs=2.5,        # hard fallback: if Smart Turn stays "incomplete" this long, end the turn anyway
            pre_speech_ms=200,
            max_duration_secs=8,
        )
    )


    context = LLMContext()  # Flows manages messages/tools per-node; start empty
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad_analyzer,
            user_turn_strategies=UserTurnStrategies(
                start=[
                    MinWordsUserTurnStartStrategy(min_words=2),  # candidate must say ≥2 words before it counts as "taking the turn" / interrupting the bot
                    TranscriptionUserTurnStartStrategy(),        # fallback so short "no"/"yes" answers aren't dropped if VAD misses them
                ],
                stop=[
                    TurnAnalyzerUserTurnStopStrategy(turn_analyzer=turn_analyzer),
                ],
            ),
        ),
        assistant_params=LLMAssistantAggregatorParams(
            enable_auto_context_summarization=False,
            # auto_context_summarization_config=LLMAutoContextSummarizationConfig(
            #     max_context_tokens=None,       # generous headroom for a single interview
            #     max_unsummarized_messages=40,   # don't trigger mid-question-cycle
            #     summary_config=LLMContextSummaryConfig(
            #         target_context_tokens=8000,
            #         min_messages_after_summary=6,  # keep the current Q&A cycle intact
            #     ),
            # ),
        ),
    )
    

    pipeline = Pipeline(
        [
            transport.input(),      # Audio FROM user (via Daily)
            stt,                     # Speech to text
            context_aggregator.user(),         # Build LLM context
            llm,                     # LLM processing
            tts,                     # Text to speech
            transport.output(),      # Audio TO user (via Daily)
            audiobuffer,            # Record conversation
            context_aggregator.assistant(),    # Track assistant responses
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
    
    flow_manager = FlowManager(
        task=worker,
        llm=llm,
        context_aggregator=context_aggregator,
        transport=transport,
    )
    _shutdown_done = False

    async def graceful_shutdown(reason: str):
        """Runs to completion instead of being torn down mid-await."""
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        logger.info(f"Graceful shutdown starting: {reason}")

        try:
            await audiobuffer.stop_recording()
        except Exception:
            logger.exception("Error stopping recording")

        try:
            await close_and_persist_interview_stage(active_session, db)
        except Exception:
            logger.exception("Error persisting interview stage")

        try:
            # force_flush is typically sync/blocking — don't block the loop
            await asyncio.to_thread(span_processor.force_flush, timeout_millis=30000)
        except Exception:
            logger.exception("Error flushing LangSmith traces")

        with contextlib.suppress(Exception):
            await worker.cancel()
    # ═══════════════════════════════════════════════════════════════
    # EVENT HANDLERS - Updated for Daily's event names
    # ═══════════════════════════════════════════════════════════════
    
    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        """Bot is ready and waiting in the room."""
        logger.info("Bot ready, waiting for user to join")
        # Don't start conversation until user joins

    # @transport.event_handler("on_participant_joined")
    # async def on_participant_joined(transport, participant):
    #     logger.info(f"Participant joined: {participant.get('user_name', 'unknown')}")
    #     await audio_buffer.start_recording()

    #     flow_manager.state["interview_state"] = active_session
    #     await flow_manager.initialize(create_greeting_node(active_session))
        
    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        logger.info(f"Participant joined: {participant.get('user_name', 'unknown')}")
        await audiobuffer.start_recording()   # renamed from audio_buffer
        flow_manager.state["interview_state"] = active_session
        await flow_manager.initialize(create_greeting_node(active_session))

    # @transport.event_handler("on_participant_left")
    # async def on_participant_left(transport, participant, reason):
    #     """User left the Daily room."""
    #     logger.info(f"Participant left: {participant.get('user_name', 'unknown')}")
    #     await audio_buffer.stop_recording()
    #     await worker.cancel()
        
    #     tracing_processor.force_flush(timeout_millis=30000)
        
    #     # Persist interview data
    #     await close_and_persist_interview_stage(active_session, db)
    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info(f"Participant left: {participant.get('user_name', 'unknown')}")
        await audiobuffer.stop_recording()
        await worker.cancel()
        await close_and_persist_interview_stage(active_session, db)

    @transport.event_handler("on_error")
    async def on_error(transport, error):
        """Handle Daily transport errors."""
        logger.error(f"Daily transport error: {error}")
    
    async def watch_stop_event():
        await stop_event.wait()
        await graceful_shutdown("stop_requested")


    # ═══════════════════════════════════════════════════════════════
    # RUN - Unchanged
    # ═══════════════════════════════════════════════════════════════
    watcher = asyncio.create_task(watch_stop_event())

    try:
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher


# ═══════════════════════════════════════════════════════════════
# CHANGED: New entry point for Daily - no webrtc_connection needed
# ═══════════════════════════════════════════════════════════════
async def run_bot_entrypoint(
    room_url: str,
    token: str,
    stage_id: int, 
    practice_attempt_id: int,
    stop_event: asyncio.Event | None = None,   
):
    """
    Entry point called from FastAPI.
    
    Args:
        room_url: The Daily.co room URL (e.g., "https://your-domain.daily.co/abc123")
        stage_id: Interview stage ID
        practice_attempt_id: Practice Attempt ID
    """
    # ═══════════════════════════════════════════════════════════════
    # CHANGED: Create DailyTransport instead of SmallWebRTCTransport
    # ═══════════════════════════════════════════════════════════════
    transport = DailyTransport(
        room_url=room_url,
        token=token,  
        bot_name="Interview Bot",
        params=DailyParams(
            api_key=os.getenv("DAILY_API_KEY"),
            audio_in_enabled=True,      # Hear the user
            audio_out_enabled=True,     # Speak to the user
            camera_out_enabled=False,   # No video from bot
        ),
    )

    # Fresh DB session that lives as long as the call
    async with AsyncSessionLocal() as db:
        try:
            await run_bot(transport, stage_id, practice_attempt_id, db, stop_event)
        except asyncio.CancelledError:
            logger.info("Bot task was cancelled")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
        finally:
            # Cleanup Daily connection
            await transport.cleanup()
            logger.info("Bot cleaned up")


