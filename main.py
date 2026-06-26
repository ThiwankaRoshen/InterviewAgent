import asyncio
import os
import sys
from dotenv import load_dotenv
from loguru import logger

# Core Pipecat Pipeline Infrastructure
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams
from pipecat.pipeline.worker import PipelineWorker
from pipecat.workers.runner import WorkerRunner

# Context Management & Framework Frames
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.frames.frames import LLMContextFrame

# AI Services (Using OpenAI Service for GitHub Models)
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.openai.llm import OpenAILLMService# <-- Swapped to OpenAI service

# Local Audio Transport Architecture
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer

load_dotenv()
logger.remove()
logger.add(sys.stderr, level="INFO")

async def main():
    # Configure Local Microphone and Speaker Parameters
    params = LocalAudioTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer()
    )
    
    # Initialize the Transport
    transport = LocalAudioTransport(params=params)

    # Instantiate AI Services
    stt = AssemblyAISTTService(api_key=os.getenv("ASSEMBLYAI_API_KEY"))
    
    # ✅ Redirect OpenAILLMService to GitHub Models Endpoint
    llm = OpenAILLMService(
        api_key=os.getenv("GITHUB_TOKEN"),
        base_url="https://models.github.ai/inference",
        model="openai/gpt-4o-mini"
    )

    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramTTSService.Settings(voice="aura-asteria-en")
    )

    # Conversation Management
    system_prompt = (
        "You are an expert, professional technical interviewer evaluating a software engineer. "
        "Keep your responses conversational, concise, and focused. "
        "Ask exactly ONE clear technical question at a time, then wait for the candidate's answer."
    )

    context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
    context_aggregator = LLMContextAggregatorPair(context)

    # Functional Processing Graph
    pipeline = Pipeline([
        transport.input(),                  # Local Microphone
        stt,                                # AssemblyAI
        context_aggregator.user(),          
        llm,                                # OpenAI client targeting GitHub Models
        tts,                                # Deepgram
        transport.output(),                 # Local Speakers
        context_aggregator.assistant()      
    ])

    # Consolidated Worker and Runner Architecture
    pipeline_params = PipelineParams(allow_interruptions=True)
    worker = PipelineWorker(pipeline, params=pipeline_params)

    # Pass the context memory structure inside the generalized LLMContextFrame
    context.add_message({"role": "user", "content": "Hello, I am ready to start my technical interview."})
    await worker.queue_frame(LLMContextFrame(context))

    runner = WorkerRunner()
    
    logger.info("Starting Interview Agent locally via GitHub Models. Speak into your microphone!")
    await runner.run(worker)

if __name__ == "__main__":
    asyncio.run(main())