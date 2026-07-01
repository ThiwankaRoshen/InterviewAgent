from pydantic import BaseModel, Field
from typing import List
import asyncio 
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate



class InterviewStagePlan(BaseModel):
    stage_order: int = Field(..., description="The sequential order of the interview stage.")
    stage_name: str = Field(..., description="Name of the stage, e.g., 'System Design'.")
    stage_description: str = Field(..., description="Detailed instructions on what this specific stage covers.")
    objective: str = Field(..., description="The core goal or target evaluation of this stage.")

class InterviewPlan(BaseModel):
    candidate_summary: str = Field(..., description="A heavily compressed (~300 token) profile of the candidate containing core stack, strengths, and weaknesses.")
    candidate_strengths: List[str] = Field(..., description="Key technical or soft strengths identified.")
    candidate_weaknesses: List[str] = Field(..., description="Areas needing deeper evaluation or missing skills.")
    interview_focus: List[str] = Field(..., description="Core themes the entire interview process must target.")
    stages: List[InterviewStagePlan] = Field(..., description="The ordered list of planned interview stages.")

class InterviewQuestion(BaseModel):
    question: str = Field(..., description="The interview question text.")
    expected_behavior: str = Field(..., description="What a strong answer should demonstrate or contain.")

class StageGeneration(BaseModel):
    interviewer_persona: str = Field(..., description="The dynamic persona profile for the interviewer of this stage.")
    questions: List[InterviewQuestion] = Field(..., description="List of questions tailored to this stage and the candidate profile.")

class StageBase(BaseModel):
    stage_order: int
    stage_name: str
    stage_description: str
    interviewer_persona: str
    questions_and_answers: List[InterviewQuestion]
    

    
PLANNER_SYSTEM_PROMPT = """You are an expert Talent Acquisition Architect and Lead Technical Recruiter.
Your job is to analyze a candidate's context (Resume, Job Description, Company Profile, and extra notes) and construct a tailored, strategic interview plan.

Strict Rules:
1. Synthesize and compress the candidate's background into a highly dense `candidate_summary` (roughly 200-300 tokens) focusing on core experience, standout projects, and tech stack match.
2. Identify explicit strengths and gaps/weaknesses relative to the Job Description.
3. Define an ordered sequence of focused interview stages. Do NOT generate interviewers or specific questions yet. Only define the metadata, description, and objective for each stage.
"""

STAGE_SYSTEM_PROMPT = """You are a specialized AI Interviewer Generator operating as a worker node.
Your task is to take a high-level interview stage plan and flesh out a hyper-realistic interviewer persona along with targeted, high-signal questions.

You will be given:
- The compressed candidate profile (Summary, Strengths, Weaknesses)
- The specific Stage Info (Name, Description, Objective)

Guidelines:
1. Craft a distinct, realistic `interviewer_persona`. The persona must match the domain (e.g., a warm HR Specialist for Culture, a demanding Principal Architect for System Design).
2. Generate highly contextual questions that directly cross-examine the candidate's resume/strengths or probe into their specific weaknesses within the scope of this stage.
3. Every question must include an explicit `expected_behavior` playbook detailing what specific signals or anti-patterns to watch out for.
""" 

class InterviewPlanner:
    def __init__(self, structured_llm: Runnable):
        """
        structured_llm must be an LLM instance already bound with 
        .with_structured_output(InterviewPlan)
        """
        self.model = structured_llm
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", PLANNER_SYSTEM_PROMPT),
            ("user", """
            ### Candidate CV:
            {cv_text}
            
            ### Job Description:
            {jd_text}
            
            ### Company Information:
            {company_info}
            
            ### Additional Context/Notes:
            {additional_notes}
            """)
        ])
        # Build an execution chain
        self.chain = self.prompt | self.model

    async def plan_interview(
        self, cv_text: str, jd_text: str, company_info: str, additional_notes: str
    ) -> InterviewPlan:
        return await self.chain.ainvoke({
            "cv_text": cv_text,
            "jd_text": jd_text,
            "company_info": company_info,
            "additional_notes": additional_notes
        })
         
          

class StageGenerator:
    def __init__(self, structured_llm: Runnable):
        """
        structured_llm must be an LLM instance already bound with 
        .with_structured_output(StageGeneration)
        """
        self.model = structured_llm
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", STAGE_SYSTEM_PROMPT),
            ("user", """
            ### Compressed Candidate Summary:
            {candidate_summary}
            
            ### Target Interview Stage Plan:
            Stage Name: {stage_name}
            Description: {stage_description}
            Objective: {objective}
            """)
        ])
        self.chain = self.prompt | self.model

    async def generate_stage_content(
        self, candidate_summary: str, stage_plan: InterviewStagePlan
    ) -> StageGeneration:
        return await self.chain.ainvoke({
            "candidate_summary": candidate_summary,
            "stage_name": stage_plan.stage_name,
            "stage_description": stage_plan.stage_description,
            "objective": stage_plan.objective
        })



class InterviewOrchestrator:
    def __init__(self, planner_llm, stage_llm):
        self.planner = InterviewPlanner(planner_llm)
        self.stage_generator = StageGenerator(stage_llm)

    async def run_pipeline(
        self, cv_text: str, jd_text: str, company_info: str, additional_notes: str
    ) -> List[StageBase]:
        
        # Phase 1: Sequential Planning call
        plan: InterviewPlan = await self.planner.plan_interview(
            cv_text=cv_text, 
            jd_text=jd_text, 
            company_info=company_info, 
            additional_notes=additional_notes
        )
        
        # Phase 2: Parallelizing worker execution with asyncio.gather
        tasks = [
            self.stage_generator.generate_stage_content(plan.candidate_summary, stage)
            for stage in plan.stages
        ]
        
        generated_stages: List[StageGeneration] = await asyncio.gather(*tasks)
        
        # Phase 3: Zipping structural plans with dynamic content
        final_interview_pipeline: List[StageBase] = []
        for stage_plan, generated_content in zip(plan.stages, generated_stages):
            merged_stage = StageBase(
                stage_order=stage_plan.stage_order,
                stage_name=stage_plan.stage_name,
                stage_description=stage_plan.stage_description,
                interviewer_persona=generated_content.interviewer_persona,
                questions=generated_content.questions
            )
            final_interview_pipeline.append(merged_stage)
            
        return final_interview_pipeline