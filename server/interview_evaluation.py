from datetime import datetime, UTC
import json
from pathlib import Path

from langchain_mistralai import ChatMistralAI
import schemas
import asyncio
import os
from typing import List

import models
from cv_parser import parse_using_pymupdf, LangChainResumeParser
from interview_gen import InterviewOrchestrator, InterviewPlan, StageGeneration, stringify_stage
from interview_evaluation_utils import markdown_to_pdf
from settings import settings
from ws_connection_manager import manager

import logging

async def trigger_stage_evaluation_pipeline(active_session):
    """
    Evaluate interview answers and generate a markdown report + PDF.
    """

    llm = ChatMistralAI(
        model=settings.MISTRAL_MODEL,
        temperature=0,
        max_retries=2,
        mistral_api_key=settings.MISTRAL_API_KEY
    )
    

    interview_text = ""

    for answer in active_session.answers_log:

        interview_text += f"""
Question:
{answer["question_text"]}

Expected Behaviour:
{answer["behaviour"]}

Candidate Answer:
{answer["answer_text"]}

---------------------------------------
"""

    prompt = f"""
You are a senior interview evaluator.

Evaluate the candidate's interview.

Return your response ONLY in Markdown.

The report should contain:

# Interview Evaluation

## Overall Score
- Overall score out of 100

## Strengths

- Bullet list

## Weaknesses

- Bullet list

## Question-by-Question Feedback

For every question include

### Question X

Score:
Strengths:
Improvements:

## Communication Assessment

Discuss confidence, clarity, pacing and professionalism.

## Final Recommendation

State whether the candidate would likely pass this stage and why.

Interview:

{interview_text}
"""

    response = await llm.ainvoke(prompt)

    markdown_report = response.content

    reports_dir = Path("medai/reports")
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = reports_dir / f"practice_{active_session.practice_session_id}__{active_session.stage_id}{timestamp}.md"
    pdf_path = reports_dir / f"practice_{active_session.practice_session_id}_{timestamp}.pdf"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_report)

    markdown_to_pdf(
        markdown_report,
        str(pdf_path),
    )

    print(f"Markdown saved to {md_path}")
    print(f"PDF saved to {pdf_path}")