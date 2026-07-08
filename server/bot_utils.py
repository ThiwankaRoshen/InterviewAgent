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
You are an AI interviewer conducting a structured interview.

You are NOT a general conversational assistant.
You are executing a predefined interview workflow.

[INTERVIEW STAGE]
Stage Order: {stage.stage_order}
Stage Name: {stage.stage_name}
Evaluation Focus:
{stage.stage_description}


[PERSONA]
{stage.interviewer_persona}


[CORE INTERVIEW RULES]

1. At the beginning of the interview:
   - Greet the candidate politely.
   - Introduce yourself briefly.
   - Explain that the interview will begin.
   - Do NOT ask the first interview question yourself.

2. QUESTION CONTROL:
   - The interview questions are managed ONLY through the `get_current_question, get_next_question` tools.
   - NEVER invent, modify, summarize, or create your own interview questions.
   - NEVER continue with an improvised conversation. 

3. INTERVIEW FLOW:
   Follow this exact loop after greeting:

   a. Call `get_current_question`.
   b. Ask the returned question exactly as provided.
   c. Wait for the candidate's answer.
   d. Evaluate the answer internally.
   e. Call `submit_answer_and_metrics`.
   f. Decide whether clarification is required.
   g. If needed, use `inject_followup_question`.
   h. Otherwise call `get_next_question` again.

4. FOLLOW-UP QUESTIONS:
   - Only create follow-up questions when the candidate answer requires clarification.
   - Follow-ups must not replace planned questions.
   - After a follow-up, Call `submit_answer_and_metrics` and return to the planned question sequence.

5. STRICT SEQUENCE:
   - The predefined question order must never change.
   - Never skip questions.
   - Never revisit previous questions.
   - Never end the interview early unless `get_next_question` returns completion.

6. VOICE OPTIMIZATION:
   - Keep responses short and natural.
   - Avoid long explanations.
   - Ask one question at a time.
   - Do not reveal evaluation criteria.

7. COMPLETION:
   When `get_next_question` returns status=complete:

   a. Do NOT immediately end the interview.
   b. Ask the candidate:
      "Thank you for your time. Do you have any questions for me?"
   c. Wait for the candidate response.
   d. Call `submit_answer_and_metrics` to log their question as the answer.
   e. Provide a brief closing statement.
   f. End the interview.


Your primary responsibility is to execute the interview workflow, not to have a free-form conversation.
""".strip()

class ActiveInterviewState:
    def __init__(self, practice_attempt_id: int, stage_id: int,  questions_and_answers_json: str, stage_name: str, stage_description: str):
        self.practice_attempt_id = practice_attempt_id
        self.stage_id = stage_id
        self.stage_name = stage_name
        self.stage_description = stage_description
        # Parse the JSON string containing the static questions from the Stage template
        self.master_questions: List[Dict[str, Any]] = json.loads(questions_and_answers_json)

        
        self.current_index = 0
        self.answers_log: List[Dict[str, Any]] = []
        self.is_followup = False
        
    def set_followup(self):
        self.is_followup = True
    
    def get_current_question(self) -> Optional[Dict[str, Any]]:
        """Returns the current master question tracking metadata."""
        if self.current_index < len(self.master_questions):
            return self.master_questions[self.current_index]
        return None

    def advance_question(self):
        """Moves the pointer forward to the next master question."""
        self.is_followup = False
        self.current_index += 1

    def log_response(self,  question_text: str, answer_text: str, behaviour: str):
        """Appends an execution record to RAM."""
        
        self.answers_log.append({ 
            "question_order": len(self.answers_log) + 1,
            "question_text": question_text,
            "behaviour": behaviour,
            "answer_text": answer_text,
            "expected_behavior": "This was a Follow up by interviewer" if self.is_followup 
                                    else self.master_questions[self.current_index - 1]["expected_behavior"],
        })

        
        


def make_interview_tools(active_session: ActiveInterviewState):
    """Return (tools_schema, handlers) bound to this call's state."""
    async def get_current_question(params: FunctionCallParams):
        
        node = active_session.get_current_question()
        if not node:
            await params.result_callback(
                {"status": "complete", "message": "No more planned questions. Wrap up the interview."}
            )
            return
        await params.result_callback({
            "status": "ongoing",
            "question": node["question"],
            "expected_behavior": node.get("expected_behavior", ""),
        })
    
    async def get_next_question(params: FunctionCallParams):
        active_session.advance_question()
        
        node = active_session.get_current_question()
        if not node:
            await params.result_callback(
                {"status": "complete", "message": "No more planned questions. Wrap up the interview."}
            )
            return
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
        active_session.set_followup()
        await params.result_callback({
            "status": "acknowledged",
            "instruction": f"Proceed to speak this follow-up question directly to candidate: {a['followup_text']}",
        })
    


    tools_schema = ToolsSchema(standard_tools=[
        FunctionSchema(
            name="get_current_question",
            description="Fetch the current interview question.",
            properties={},
            required=[],
        ),
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
        "get_current_question": get_current_question,
        "get_next_question": get_next_question,
        "submit_answer_and_metrics": submit_answer_and_metrics,
        "inject_followup_question": inject_followup_question,
    }
    return tools_schema, handlers
    

async def initialize_active_session_state(stage_id: int, practice_attempt_id: int, db: AsyncSession) -> ActiveInterviewState:
    # Pull the JSON array definition out of the master template stage
    stage = await db.execute(
        select(models.Stage)
        .where(models.Stage.id == stage_id)
    )
    stage = stage.scalar_one_or_none()
    
    if not stage:
        raise ValueError("Stage blueprint configuration does not exist.")
        
    # Instantiate the memory tracker instance to be consumed by Pipecat hooks
    return ActiveInterviewState(
        practice_attempt_id=practice_attempt_id, 
        stage_id=stage_id,
        questions_and_answers_json=stage.questions_and_answers,
        stage_description=stage.stage_description,
        stage_name=stage.stage_name,
    )


async def close_and_persist_interview_stage(active_session: ActiveInterviewState, db: AsyncSession):
    """
    Flushes the memory state buffer straight to SQLite in a single transaction 
    and opens the floor for evaluation triggers.
    """
 
 
    # 1. Map raw list dictionaries to explicit Answer object models
    bulk_answers = [
        models.Answer(
            practice_attempt_id=active_session.practice_attempt_id,
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


