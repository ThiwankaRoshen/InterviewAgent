from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from interview_evaluation import trigger_stage_evaluation_pipeline
from pipecat.flows import FlowManager, NodeConfig, FlowsFunctionSchema
from pipecat.flows.types import FlowArgs


# ─────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────
class ActiveInterviewState:

    def __init__(
        self,
        practice_attempt_id: int,
        stage_id: int,
        questions_and_answers_json: str,
        stage_name: str,
        stage_description: str,
        interviewer_persona: str,
    ):
        self.practice_attempt_id = practice_attempt_id
        self.stage_id = stage_id
        self.stage_name = stage_name
        self.stage_description = stage_description
        self.interviewer_persona = interviewer_persona
        self.master_questions: List[Dict[str, Any]] = json.loads(questions_and_answers_json)

        self.current_index = 0
        self.is_followup = False
        self.followup_text: Optional[str] = None
        self.answers_log: List[Dict[str, Any]] = []
        self.followup_count = 0
        self.max_followups_per_question = 1

    # -- read helpers -----------------------------------------------------
    def current_question_text(self) -> str:
        if self.is_followup:
            return self.followup_text or ""
        return self.master_questions[self.current_index]["question"]

    def current_expected_behavior(self) -> str:
        if self.is_followup:
            return "This was a follow-up question by the interviewer."
        return self.master_questions[self.current_index].get("expected_behavior", "")

    def has_more_questions(self) -> bool:
        return self.current_index < len(self.master_questions)

    # -- mutation helpers ---------------------------------------------------
    def record_answer(self, answer_text: str, confidence: str, pacing: str) -> None:
        self.answers_log.append(
            {
                "question_order": len(self.answers_log) + 1,
                "question_text": self.current_question_text(),
                "behaviour": f"Confidence: {confidence}. Pacing/Delivery: {pacing}.",
                "answer_text": answer_text,
                "expected_behavior": self.current_expected_behavior(),
            }
        )

    def record_closing(self, response_text: str) -> None:
        self.answers_log.append(
            {
                "question_order": len(self.answers_log) + 1,
                "question_text": "Do you have any questions for me?",
                "behaviour": "",
                "answer_text": response_text,
                "expected_behavior": "Closing remarks",
            }
        )

    def set_followup(self, followup_text: str) -> None:
        self.is_followup = True
        self.followup_text = followup_text
        self.followup_count += 1

    def advance(self) -> None:
        self.is_followup = False
        self.followup_text = None
        self.current_index += 1
        self.followup_count = 0


# ─────────────────────────────────────────────────────────────────────────
# DB helpers (same behavior as bot_utils.py, just relocated)
# ─────────────────────────────────────────────────────────────────────────
async def load_stage(stage_id: int, db: AsyncSession) -> models.Stage:
    query = (
        select(models.Stage)
        .where(models.Stage.id == stage_id)
        .options(selectinload(models.Stage.session))
    )
    result = await db.execute(query)
    stage = result.scalar_one_or_none()
    if not stage:
        raise ValueError(f"Stage configuration with ID {stage_id} not found.")
    return stage


async def initialize_active_session_state(
    stage_id: int, practice_attempt_id: int, db: AsyncSession
) -> ActiveInterviewState:
    stage = await load_stage(stage_id, db)
    return ActiveInterviewState(
        practice_attempt_id=practice_attempt_id,
        stage_id=stage_id,
        questions_and_answers_json=stage.questions_and_answers,
        stage_description=stage.stage_description,
        stage_name=stage.stage_name,
        interviewer_persona=stage.interviewer_persona,
    )


async def close_and_persist_interview_stage(
    active_session: ActiveInterviewState, db: AsyncSession
) -> None:
    bulk_answers = [
        models.Answer(
            practice_attempt_id=active_session.practice_attempt_id,
            question_order=item["question_order"],
            question_text=item["question_text"],
            behaviour=item["behaviour"],
            answer_text=item["answer_text"],
        )
        for item in active_session.answers_log
    ]
    db.add_all(bulk_answers)
    await db.commit()
    await trigger_stage_evaluation_pipeline(active_session)


def create_greeting_node(state: ActiveInterviewState) -> NodeConfig:
    return NodeConfig(
        name="greeting",
        role_messages=[
            {
                "role": "system",
                "content": (
                    f"{state.interviewer_persona}\n\n"
                    "Your responses will be converted to audio, so keep them short, "
                    "natural, and conversational."
                ),
            }
        ],
        task_messages=[
            {
                "role": "system",
                "content": (
                    "Greet the candidate warmly, briefly introduce yourself, and let them "
                    "know the interview is about to begin. Do NOT ask the first interview "
                    "question yourself, and do not reveal how you'll be evaluating them. "
                    "As soon as you're done greeting them, call begin_interview."
                ),
            }
        ],
        functions=[
            FlowsFunctionSchema(
                name="begin_interview",
                description=(
                    "Call this immediately after greeting the candidate, to move on to "
                    "the first interview question."
                ),
                properties={},
                required=[],
                handler=_handle_begin_interview,
            )
        ],
    )


async def _handle_begin_interview(args: FlowArgs, flow_manager: FlowManager):
    state: ActiveInterviewState = flow_manager.state["interview_state"]
    return None, create_question_node(state)


def create_question_node(state: ActiveInterviewState) -> NodeConfig:
    question_text = state.current_question_text()
    kind = "follow-up" if state.is_followup else "planned"

    return NodeConfig(
        name=f"question_{state.current_index}_{'f' if state.is_followup else 'm'}",
        task_messages=[
            {
                "role": "system",
                "content": (
                    f'Ask the candidate exactly this {kind} question, word for word, and '
                    f'nothing else: "{question_text}"\n\n'
                    "Do not paraphrase it, soften it, add commentary, or ask more than one "
                    "question. Then wait for the candidate to answer.\n\n"
                    "- If the candidate asks you to repeat the question (or clearly didn't "
                    "hear it), call repeat_question.\n"
                    "- Once they give an answer, silently judge whether it's satisfactory "
                    "and clear, then call record_answer with your assessment. If it is NOT "
                    "satisfactory or clear, also fill in follow_up_text with a short, "
                    "specific clarifying question - you'll ask that next.\n"
                    "- Never invent a new planned question yourself; only these two tools "
                    "exist for a reason."
                ),
            }
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_answer",
                description=(
                    "Log the candidate's answer and delivery metrics, and say whether "
                    "the answer was satisfactory."
                ),
                properties={
                    "answer_text": {
                        "type": "string",
                        "description": "What the candidate said, in their own words.",
                    },
                    "confidence": {
                        "type": "string",
                        "description": "Perceived confidence, e.g. low / medium / high.",
                    },
                    "pacing": {
                        "type": "string",
                        "description": "Perceived pacing/delivery, e.g. rushed / steady / slow.",
                    },
                    "satisfactory": {
                        "type": "boolean",
                        "description": "True if the answer sufficiently addresses the question.",
                    },
                    "follow_up_text": {
                        "type": "string",
                        "description": (
                            "Only set when satisfactory=false: the exact follow-up "
                            "question to ask the candidate next."
                        ),
                    },
                },
                required=["answer_text", "confidence", "pacing", "satisfactory"],
                handler=_handle_record_answer,
            ),
            FlowsFunctionSchema(
                name="repeat_question",
                description="Call when the candidate asks you to repeat the current question.",
                properties={},
                required=[],
                handler=_handle_repeat_question,
            ),
        ],
    )


async def _handle_repeat_question(args: FlowArgs, flow_manager: FlowManager):
    state: ActiveInterviewState = flow_manager.state["interview_state"]
    # Re-emitting the same node is idempotent: current_index / is_followup /
    # followup_text are all unchanged, so the candidate hears the identical
    # question again.
    return {"status": "repeating"}, create_question_node(state)


async def _handle_record_answer(args: FlowArgs, flow_manager: FlowManager):
    state: ActiveInterviewState = flow_manager.state["interview_state"]
    state.record_answer(
        answer_text=args["answer_text"],
        confidence=args["confidence"],
        pacing=args["pacing"],
    )
    
    wants_followup = not args.get("satisfactory", True)
    can_still_follow_up = state.followup_count < state.max_followups_per_question

    if wants_followup and can_still_follow_up:
        follow_up = args.get("follow_up_text") or "Could you clarify or expand on that a bit more?"
        state.set_followup(follow_up)
        logger.info(f"Answer not satisfactory, asking follow-up: {follow_up}")
        return {"status": "logged"}, create_question_node(state)

    state.advance()
    if state.has_more_questions():
        return {"status": "logged"}, create_question_node(state)

    return {"status": "logged"}, create_closing_node(state)


def create_closing_node(state: ActiveInterviewState) -> NodeConfig:
    return NodeConfig(
        name="closing",
        task_messages=[
            {
                "role": "system",
                "content": (
                    "Thank the candidate for their time, then ask exactly: "
                    '"Do you have any questions for me?" Wait for their response, then '
                    'call record_closing_remarks with what they said (even if it is "no").'
                ),
            }
        ],
        functions=[
            FlowsFunctionSchema(
                name="record_closing_remarks",
                description="Log the candidate's closing question or response.",
                properties={"response_text": {"type": "string"}},
                required=["response_text"],
                handler=_handle_closing,
            )
        ],
    )


async def _handle_closing(args: FlowArgs, flow_manager: FlowManager):
    state: ActiveInterviewState = flow_manager.state["interview_state"]
    state.record_closing(args["response_text"])
    return None, create_farewell_node()


def create_farewell_node() -> NodeConfig:
    task_messages = [
        {
            "role": "system",
            "content": "Give a brief, warm closing statement, then say goodbye.",
        }
    ] 

    # Fallback if this pipecat-flows version doesn't export create_end_node.
    return NodeConfig(
        name="farewell",
        task_messages=task_messages,
        functions=[],
        post_actions=[{"type": "end_conversation"}],
    )