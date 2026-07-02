from datetime import datetime, UTC
import json
from typing import List, Dict, Any, Optional
from interview_evaluation import trigger_stage_evaluation_pipeline
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import models 
from sqlalchemy.orm import selectinload
from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema


async def generate_system_prompt(stage_id: int, db: AsyncSession) -> str:
    # 1. Fetch Stage and eagerly load the parent Session to avoid lazy-loading issues
    query = (
        select(models.Stage)
        .where(models.Stage.id == stage_id)
        .options(selectinload(models.Stage.session))  # Ensures parent session details are pulled cleanly
    )
    result = await db.execute(query)
    stage = result.scalar_one_or_none()
    
    if not stage:
        raise ValueError(f"Stage configuration with ID {stage_id} not found.")
        
    # Alias the parent session data for readability
    session = stage.session

    # 2. Build and return the compiled system prompt string directly
    return f"""
You are an advanced AI Interviewer simulation engine acting out a live voice session.

[STAGE OBJECTIVES]
- Current Stage: {stage.stage_order}
- Stage Name: {stage.stage_name}
- Focus Evaluation: {stage.stage_description}

[YOUR PERSONA & TONALITY]
{stage.interviewer_persona}

[CANDIDATE BACKGROUND CONTEXT]
- Target Job Specifications: 
{session.job_description}

- Target Company Culture/Core:
{session.company_info}

- Extra Context / Past Leakage Details:
{session.additional_info}

[CRITICAL INSTRUCTIONS]
1. Remain strictly in character based on your assigned Persona.
2. Adapt dynamically to candidate responses, analyzing confidence, clarity, and critical thinking.
3. Keep conversational turns natural, direct, and voice-optimized (avoid dense walls of text).
""".strip()

class ActiveInterviewState:
    def __init__(self, practice_session_id: int, stage_id: int,  questions_and_answers_json: str):
        self.practice_session_id = practice_session_id
        self.stage_id = stage_id
        # Parse the JSON string containing the static questions from the Stage template
        self.master_questions: List[Dict[str, Any]] = [{q_a["question"]:q_a["expected_behavior"]} 
                                                       for q_a in json.loads(questions_and_answers_json)]

        
        self.current_index = 0
        self.answers_log: List[Dict[str, Any]] = []
        
    def get_current_question(self) -> Optional[Dict[str, Any]]:
        """Returns the current master question tracking metadata."""
        if self.current_index < len(self.master_questions):
            return self.master_questions[self.current_index]
        return None

    def advance_question(self):
        """Moves the pointer forward to the next master question."""
        self.current_index += 1

    def log_response(self, question_text: str, answer_text: str, behaviour: str):
        """Appends an execution record to RAM."""
        self.answers_log.append({
            "question_order": len(self.answers_log) + 1,
            "question_text": question_text,
            "behaviour": behaviour,
            "answer_text": answer_text
        })
        


def make_interview_tools(active_session: ActiveInterviewState):
    """Return (tools_schema, handlers) bound to this call's state."""

    async def get_next_question(params: FunctionCallParams):
        node = active_session.get_current_question()
        if not node:
            await params.result_callback(
                {"status": "complete", "message": "No more planned questions. Wrap up the interview."}
            )
            return
        active_session.advance_question()
        await params.result_callback({
            "status": "ongoing",
            "question": node["question"],
            "expected_behavior": node.get("expected_behavior", ""),
        })

    async def submit_answer_and_metrics(params: FunctionCallParams):
        a = params.arguments
        behaviour = f"Confidence: {a['confidence']}. Pacing/Delivery: {a['pacing']}."
        active_session.log_response(a["question_text"], a["answer_text"], behaviour)
        await params.result_callback({"status": "success", "message": "Answer logged."})

    async def inject_followup_question(params: FunctionCallParams):
        a = params.arguments
        await params.result_callback({
            "status": "acknowledged",
            "instruction": f"Proceed to speak this follow-up question directly to candidate: {a['followup_text']}",
        })

    tools_schema = ToolsSchema(standard_tools=[
        FunctionSchema(
            name="get_next_question",
            description="Fetch the next planned interview question.",
            properties={},
            required=[],
        ),
        FunctionSchema(
            name="submit_answer_and_metrics",
            description="Log the candidate's answer plus vocal delivery metrics.",
            properties={
                "question_text": {"type": "string"},
                "answer_text": {"type": "string"},
                "confidence": {"type": "string"},
                "pacing": {"type": "string"},
            },
            required=["question_text", "answer_text", "confidence", "pacing"],
        ),
        FunctionSchema(
            name="inject_followup_question",
            description="Register a dynamic follow-up question that doesn't advance the script.",
            properties={
                "followup_text": {"type": "string"},
                "reason": {"type": "string"},
            },
            required=["followup_text"],
        ),
    ])

    handlers = {
        "get_next_question": get_next_question,
        "submit_answer_and_metrics": submit_answer_and_metrics,
        "inject_followup_question": inject_followup_question,
    }
    return tools_schema, handlers
    

async def initialize_active_session_state(stage_id: int, practice_session_id: int, db: AsyncSession) -> ActiveInterviewState:
    # Pull the JSON array definition out of the master template stage
    result = await db.execute(
        select(models.Stage.questions_and_answers)
        .where(models.Stage.id == stage_id)
    )
    qas_json = result.scalar_one_or_none()
    
    if not qas_json:
        raise ValueError("Stage blueprint configuration does not exist.")
        
    # Instantiate the memory tracker instance to be consumed by Pipecat hooks
    return ActiveInterviewState(
        practice_session_id=practice_session_id, 
        stage_id=stage_id,
        questions_and_answers_json=qas_json
    )


async def close_and_persist_interview_stage(active_session: ActiveInterviewState, db: AsyncSession):
    """
    Flushes the memory state buffer straight to SQLite in a single transaction 
    and opens the floor for evaluation triggers.
    """
    # 0. Init a PracticeStage record to mark the end of this run
    practice_stage = models.PracticeStage(
        practice_session_id=active_session.practice_session_id,
    )
    db.add(practice_stage)
    await db.commit()
    await db.refresh(practice_stage)
    
    # 1. Map raw list dictionaries to explicit Answer object models
    bulk_answers = [
        models.Answer(
            practice_stage_id=practice_stage.id,
            question_order=item["question_order"],
            question_text=item["question_text"],
            behaviour=item["behaviour"],
            answer_text=item["answer_text"]
        )
        for item in active_session.answers_log
    ]
    
    # 2. Add and commit all entities instantly
    db.add_all(bulk_answers)
    await db.commit()
    
    # 3. Trigger Evaluation Core Processing Pipelines
    # At this point, your backend can safely execute an async worker task to read 
    # these written answers, contrast them against expectations, and generate the summary report.
    await trigger_stage_evaluation_pipeline(active_session)


