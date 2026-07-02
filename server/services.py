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



async def create_interview_session_service(
    session: models.Session,
) -> List[schemas.StageBase]:
    
    # 1. Instantiate basic LangChain OpenAI model wrappers.
    # base_llm = ChatOpenAI(
    #         base_url=settings.BASE_URL_INTERVIEW_GEN,
    #         model=settings.MODEL_INTERVIEW_GEN,
    #         temperature=0.2,
    #         api_key=settings.GITHUB_TOKEN_INTERVIEW_GEN,
    #     ) 
    
    base_llm = ChatMistralAI(
            model="mistral-small-latest",
            temperature=0,
            max_retries=2,
            mistral_api_key=settings.MISTRAL_API_KEY
        )
    # 2. Bind structured output formats natively using LangChain
    planner_llm = base_llm.with_structured_output(InterviewPlan)
    stage_llm = base_llm.with_structured_output(StageGeneration)

    # 3. Supply to the Orchestrator
    orchestrator = InterviewOrchestrator(planner_llm=planner_llm, stage_llm=stage_llm)

    # cv_content = parse_using_pymupdf(session.cv_file_path)
    
    parser = LangChainResumeParser()
    cv_content = parser.parse(session.cv_file_path)
    
    
    
    jd = session.job_description
    

    company_description = session.company_info
    additional_info = session.additional_info
    
    # 4. Trigger Orchestration Pipeline
    pipeline_result = await orchestrator.run_pipeline(
        cv_text=cv_content,
        jd_text=jd,
        company_info=company_description,
        additional_notes=additional_info,
    )

    return  stringify_stage(pipeline_result)


# async def main():
#     output = await create_interview_session_service()
#     print(output)
    
# def run_main():
#     asyncio.run(main())
    
# if __name__ == "__main__":
#     run_main()