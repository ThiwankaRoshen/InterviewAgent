# mock_services.py
"""Mocked versions of services.py — no DB, no async, just fixtures."""

import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from pipecat.services.llm_service import FunctionCallParams
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema


# ---------------------------------------------------------------------------
# Fake "DB rows" as plain dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MockSession:
    cv_path: str = "cv/john_doe.pdf"
    job_description: str = "Backend Engineer, Python/FastAPI, 3+ YOE."
    company_info: str = "Series B fintech startup, fast-paced, remote-first."
    additional_info: str = "Candidate mentioned strong interest in system design."


@dataclass
class MockStage:
    stage_order: int = 1
    stage_name: str = "Technical Screening"
    stage_description: str = "Assess core Python and system design fundamentals."
    interviewer_persona: str = (
        "You are Priya, a friendly but rigorous senior engineer conducting "
        "a technical screen. Warm tone, but you push for specifics."
    )
    session: MockSession = None

    def __post_init__(self):
        if self.session is None:
            self.session = MockSession()


MOCK_QUESTIONS = [
    {
        "question": "Can you walk me through a time you optimized a slow database query?",
        "expected_behavior": "Look for specifics: profiling, indexing, before/after metrics.",
    },
    {
        "question": "How would you design a rate limiter for a public API?",
        "expected_behavior": "Look for token bucket / sliding window reasoning, storage tradeoffs.",
    },
    {
        "question": "Tell me about a disagreement you had with a teammate on a technical decision.",
        "expected_behavior": "Look for concrete conflict-resolution, not just 'we talked it out'.",
    },
]


# ---------------------------------------------------------------------------
# Prompt generation — sync, no DB
# ---------------------------------------------------------------------------

def generate_system_prompt_mock(stage: MockStage) -> str:
    session = stage.session
    return f"""
You are an advanced AI Interviewer simulation engine acting out a live voice session.

[STAGE OBJECTIVES]
- Current Stage: {stage.stage_order}
- Stage Name: {stage.stage_name}
- Focus Evaluation: {stage.stage_description}

[YOUR PERSONA & TONALITY]
{stage.interviewer_persona}

[CANDIDATE BACKGROUND CONTEXT]
- CV Reference Key: {session.cv_path}
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
4. Call get_next_question when ready to move to the next question. Call submit_answer_and_metrics
   right after the candidate finishes answering. Use inject_followup_question sparingly to dig deeper.
""".strip()


# ---------------------------------------------------------------------------
# In-memory interview state (identical logic to your real ActiveInterviewState,
# just seeded from MOCK_QUESTIONS instead of a JSON column)
# ---------------------------------------------------------------------------

class ActiveInterviewState:
    def __init__(self, practice_stage_id: int, questions: List[Dict[str, Any]]):
        self.practice_stage_id = practice_stage_id
        self.master_questions = questions
        self.current_index = 0
        self.answers_log: List[Dict[str, Any]] = []

    def get_current_question(self) -> Optional[Dict[str, Any]]:
        if self.current_index < len(self.master_questions):
            return self.master_questions[self.current_index]
        return None

    def advance_question(self):
        self.current_index += 1

    def log_response(self, question_text: str, answer_text: str, behaviour: str):
        self.answers_log.append({
            "question_order": len(self.answers_log) + 1,
            "question_text": question_text,
            "behaviour": behaviour,
            "answer_text": answer_text,
        })


# ---------------------------------------------------------------------------
# Tools — identical to the real ones, just no DB writes at the end
# ---------------------------------------------------------------------------

def make_interview_tools(active_session: ActiveInterviewState):

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
        print("LOGGED (mock, not persisted):", active_session.answers_log[-1])
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