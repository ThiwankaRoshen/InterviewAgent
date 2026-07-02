import json

from langchain_mistralai import ChatMistralAI
import schemas
import asyncio
import os
from typing import List
from langchain_openai import ChatOpenAI

import models
from cv_parser import parse_using_pymupdf, LangChainResumeParser
from interview_gen import InterviewOrchestrator, InterviewPlan, StageGeneration, stringify_stage
from settings import settings
from ws_connection_manager import manager

import logging

logger = logging.getLogger(__name__)


async def create_interview_session_service(
    session: models.Session,
) -> List[schemas.StageBase]:
    """Generate interview plan with real-time progress updates."""
    
    session_id = session.id
    
    # Initialize LLM
    await manager.send_progress(session_id, "Initializing AI models", 5)
    
    base_llm = ChatMistralAI(
        model=settings.MISTRAL_MODEL,
        temperature=0,
        max_retries=2,
        mistral_api_key=settings.MISTRAL_API_KEY
    )
    
    planner_llm = base_llm.with_structured_output(InterviewPlan)
    stage_llm = base_llm.with_structured_output(StageGeneration)
    orchestrator = InterviewOrchestrator(
        planner_llm=planner_llm,
        stage_llm=stage_llm
    )
    
    # Parse CV
    await manager.send_progress(session_id, "Parsing CV document", 15)
    
    try:
        parser = LangChainResumeParser()
        cv_content = parser.parse(session.cv_file_path)
    except Exception as e:
        logger.error(f"CV parsing failed: {e}")
        await manager.send_error(session_id, "cv_parse_failed", str(e))
        raise
    
    await manager.send_progress(session_id, "CV parsed successfully", 25)
    
    # Prepare context
    jd = session.job_description
    company_description = session.company_info
    additional_info = session.additional_info
    
    
    await manager.send_progress(session_id, "Generating interview plan", 30)
    
    try:
        pipeline_result = await orchestrator.run_pipeline(
            cv_text=cv_content,
            jd_text=jd,
            company_info=company_description,
            additional_notes=additional_info, 
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        await manager.send_error(session_id, "pipeline_failed", str(e))
        raise
    
    await manager.send_progress(session_id, "Finalizing interview plan", 95)
    
    result = [stringify_stage(result) for result in pipeline_result]
    
    await manager.send_progress(session_id, "Complete", 100)
    await manager.send(session_id, {
        "type": "complete",
        "stage_count": len(result),
    })
    
    return result