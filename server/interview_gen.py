import json
import operator
from typing import List, Annotated, TypedDict, Optional

from pydantic import BaseModel, Field
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

import schemas


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class StageSkeleton(BaseModel):
    """Bare-bones stage metadata, produced WITHOUT looking at the CV."""
    stage_order: int = Field(..., description="The sequential order of the interview stage.")
    stage_name: str = Field(..., description="Name of the stage, e.g., 'System Design'.")
    stage_description: str = Field(..., description="Detailed instructions on what and How this specific stage covers.")
    stage_requirements: list[str] = Field(..., description="Constraints for a given stage.")


class InterviewPlanSkeleton(BaseModel):
    """Output of the planner node. Deliberately CV-free."""
    interview_focus: List[str] = Field(..., description="Core themes the entire interview process must target.")
    stages: List[StageSkeleton] = Field(..., description="The ordered list of planned interview stages.")


class StageCvContext(BaseModel):
    """Output of the per-stage CV-extraction worker."""
    cv_context: str = Field(..., description="Concise, high-signal excerpts/summary from the candidate's CV relevant ONLY to this specific interview stage.")


class InterviewStagePlan(BaseModel):
    """A stage skeleton merged with its stage-specific CV context."""
    stage_order: int
    stage_name: str
    stage_description: str
    cv_context: str = Field(..., description="Relevant Context from Candidate's CV for this interview stage.")
    stage_requirements: list[str]


class InterviewQuestion(BaseModel):
    question: str = Field(..., description="The interview question text.")
    expected_behavior: str = Field(..., description="What a strong answer should demonstrate or contain.")


class StageGeneration(BaseModel):
    interviewer_persona: str = Field(..., description="The dynamic persona profile for the interviewer of this stage.")
    questions_and_answers: List[InterviewQuestion] = Field(..., description="List of questions and expected answers tailored to this stage and the candidate profile.")


class StageBase(BaseModel):
    stage_order: int
    stage_name: str
    stage_description: str
    interviewer_persona: str
    questions_and_answers: List[InterviewQuestion]


def stringify_stage(stage: StageBase) -> schemas.StageBase:
    return schemas.StageBase(
        stage_order=stage.stage_order,
        stage_name=stage.stage_name,
        stage_description=stage.stage_description,
        interviewer_persona=stage.interviewer_persona,
        questions_and_answers=json.dumps(
            [q.model_dump() for q in stage.questions_and_answers],
            indent=2,
        ),
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are an expert Talent Acquisition Architect and Lead Technical Recruiter.
Your job is to analyze the Job Description, Company Profile, and extra notes and construct a tailored, strategic interview plan.

Strict Rules:
1. Base the plan ONLY on the Job Description, Company Information, and Additional Notes. You do NOT have access to any specific candidate's CV at this stage, and must not assume one.
2. Define `interview_focus`: the core themes the entire interview process must target, derived from the role's requirements.
3. Define an ordered sequence of focused interview stages (`stage_order`, `stage_name`, `stage_description`). Do NOT generate interviewers or specific questions yet, and do NOT reference any candidate-specific content.
4. Remember to extract any explicit constraints mentioned in the context (e.g. number of questions per stage). Store any such constraint for a given stage in that stage's `stage_requirements` field. If nothing specific was stated for a stage, leave `stage_requirements` as null — do not invent constraints.

"""

CV_CONTEXT_SYSTEM_PROMPT = """You are a specialized CV Analyst operating as a worker node in a larger interview-generation pipeline.
Your only job is to read the candidate's full CV and extract the subset of content that is directly relevant to ONE specific interview stage.

You will be given:
- The full candidate CV text
- The name and description of a single interview stage

Guidelines:
1. Extract and condense only the CV content relevant to this stage's topic and scope (e.g. name of the candidate, relevent projects, roles, skills, achievements, gaps).
2. Do not include content irrelevant to this stage, and do not try to summarize the entire CV.
3. Output should be dense, factual, high-signal excerpts an interviewer can act on directly for this stage only.
"""

STAGE_SYSTEM_PROMPT = """You are a specialized AI Interviewer Generator operating as a worker node.
Your task is to take a fully-scoped interview stage (including the CV context already extracted for it) and flesh out a hyper-realistic interviewer persona along with targeted, high-signal questions.

You will be given:
- The specific Stage Info (Name, Description)
- The CV context already extracted specifically for this stage
- Global Interview Context (Full Interview Process Focus and Previous and Next Stage names/descriptions)

Guidelines:
1. Craft a distinct, realistic `interviewer_persona`. The persona must match the domain (e.g., a warm HR Specialist for Culture, a demanding Principal Architect for System Design).
2. Generate highly contextual questions that directly cross-examine the candidate's resume/strengths or probe into their specific weaknesses, using the CV context provided for this stage.
   questions should be without any markdown symbols to make sure tts can easily say.
3. Every question must include an explicit `expected_behavior` playbook detailing what specific signals or anti-patterns to watch out for.
4. Do not repeat topics relevant to previous or next stages (you're only given previous and next stages names/descriptions, not their CV context, to keep this stage self-contained).
5. If `stage_requirements` is provided, treat it as a hard constraint (e.g. an exact question count or a required format) and follow it exactly. If it is null, use your own judgement for scope and question count.

"""


# ---------------------------------------------------------------------------
# Graph state definitions
# ---------------------------------------------------------------------------

class OverallState(TypedDict):
    # Inputs
    cv_text: str
    jd_text: str
    company_info: str
    additional_notes: str

    # Phase 1 output (planner, CV-free)
    interview_focus: List[str]
    stage_skeletons: List[StageSkeleton]

    # Phase 2 output (accumulated from parallel per-stage CV extraction)
    stage_plans: Annotated[List[InterviewStagePlan], operator.add]
    ordered_stage_plans: List[InterviewStagePlan]

    # Phase 3 output (accumulated from parallel stage-content generation)
    generated_stages: Annotated[List[StageBase], operator.add]

    # Final, order-sorted output
    final_pipeline: List[StageBase]


class CvContextWorkerState(TypedDict):
    """Private state for each parallel CV-extraction branch."""
    cv_text: str
    stage_skeleton: StageSkeleton


class StageContentWorkerState(TypedDict):
    """Private state for each parallel stage-content-generation branch."""
    stage_plan: InterviewStagePlan
    interview_focus: List[str]
    prev_stages: List[dict]
    next_stages: List[dict]


# ---------------------------------------------------------------------------
# Chain builders
# ---------------------------------------------------------------------------

class PlannerChain:
    """Produces interview_focus + stage skeletons from JD/company/notes only."""

    def __init__(self, structured_llm: Runnable, max_retries: int = 2):
        self.model = structured_llm
        self.max_retries = max_retries
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", PLANNER_SYSTEM_PROMPT),
            ("user", """
            ### Job Description:
            {jd_text}

            ### Company Information:
            {company_info}

            ### Additional Context/Notes:
            {additional_notes}
            """)
        ])
        self.chain = self.prompt | self.model

    async def invoke(self, jd_text: str, company_info: str, additional_notes: str) -> InterviewPlanSkeleton:
        for _ in range(self.max_retries + 1):
            result = await self.chain.ainvoke({
                "jd_text": jd_text,
                "company_info": company_info,
                "additional_notes": additional_notes,
            })
            if result is not None:
                return result
        raise ValueError("Planner LLM returned None after retries. This usually happens when the model fails to use the required tool/function calling.")


class CvContextChain:
    """Extracts stage-specific high-signal CV context, one stage at a time."""

    def __init__(self, structured_llm: Runnable, max_retries: int = 2):
        self.model = structured_llm
        self.max_retries = max_retries
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", CV_CONTEXT_SYSTEM_PROMPT),
            ("user", """
            ### Candidate CV:
            {cv_text}

            ### Target Interview Stage:
            Stage Name: {stage_name}
            Description: {stage_description}
            """)
        ])
        self.chain = self.prompt | self.model

    async def invoke(self, cv_text: str, stage_skeleton: StageSkeleton) -> StageCvContext:
        for _ in range(self.max_retries + 1):
            result = await self.chain.ainvoke({
                "cv_text": cv_text,
                "stage_name": stage_skeleton.stage_name,
                "stage_description": stage_skeleton.stage_description,
            })
            if result is not None:
                return result
        raise ValueError(
            f"CvContextChain LLM returned None for stage '{stage_skeleton.stage_name}' after {self.max_retries + 1} attempts."
        )


class StageChain:
    """Generates interviewer persona + questions for one already-scoped stage."""

    def __init__(self, structured_llm: Runnable, max_retries: int = 2):
        self.model = structured_llm
        self.max_retries = max_retries
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", STAGE_SYSTEM_PROMPT),
            ("user", """
            ### Target Interview Stage Plan:
            Stage Order: {stage_order}
            Stage Name: {stage_name}
            Description: {stage_description}
            Stage Requirements: {stage_requirements}
            
            ### CV Context (extracted specifically for this stage):
            {cv_context}

            ## Global Interview Info:
            # **Previous Stages**:
            {prev_stages}

            # **Next Stages**:
            {next_stages}

            # **Interview Focus**:
            {interview_focus}
            """)
        ])
        self.chain = self.prompt | self.model

    async def invoke(
        self,
        stage_plan: InterviewStagePlan,
        interview_focus: List[str],
        prev_stages: List[dict],
        next_stages: List[dict],
    ) -> StageGeneration:
        for _ in range(self.max_retries + 1):
            result = await self.chain.ainvoke({
                "stage_order": stage_plan.stage_order,
                "stage_name": stage_plan.stage_name,
                "stage_description": stage_plan.stage_description,
                "stage_requirements": stage_plan.stage_requirements,
                "cv_context": stage_plan.cv_context,
                "prev_stages": prev_stages,
                "next_stages": next_stages,
                "interview_focus": interview_focus,
            })
            if result is not None:
                return result
        raise ValueError(
            f"StageGenerator LLM returned None for stage '{stage_plan.stage_name}' after {self.max_retries + 1} attempts. "
            "This usually happens when the model fails to use the required tool/function calling."
        )


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_interview_graph(planner_llm: Runnable, cv_context_llm: Runnable, stage_llm: Runnable):
    """
    planner_llm       must be bound with .with_structured_output(InterviewPlanSkeleton)
    cv_context_llm    must be bound with .with_structured_output(StageCvContext)
    stage_llm         must be bound with .with_structured_output(StageGeneration)
    """
    planner_chain = PlannerChain(planner_llm)
    cv_context_chain = CvContextChain(cv_context_llm)
    stage_chain = StageChain(stage_llm)

    # --- Phase 1: sequential, CV-free planning ------------------------------
    async def plan_stages_node(state: OverallState) -> dict:
        skeleton = await planner_chain.invoke(
            jd_text=state["jd_text"],
            company_info=state["company_info"],
            additional_notes=state["additional_notes"],
        )
        print(f"Generated Interview Plan Skeleton: {skeleton}")
        return {
            "interview_focus": skeleton.interview_focus,
            "stage_skeletons": skeleton.stages,
        }

    # --- Phase 2 fan-out: one CV-extraction call per stage, in parallel -----
    def fan_out_to_cv_context(state: OverallState) -> List[Send]:
        return [
            Send("extract_cv_context", {"cv_text": state["cv_text"], "stage_skeleton": skeleton})
            for skeleton in state["stage_skeletons"]
        ]

    async def extract_cv_context_node(state: CvContextWorkerState) -> dict:
        skeleton = state["stage_skeleton"]
        extracted = await cv_context_chain.invoke(state["cv_text"], skeleton)
        stage_plan = InterviewStagePlan(
            stage_order=skeleton.stage_order,
            stage_name=skeleton.stage_name,
            stage_description=skeleton.stage_description,
            stage_requirements=skeleton.stage_requirements,
            cv_context=extracted.cv_context,
        )
        return {"stage_plans": [stage_plan]}

    # --- Join point after phase 2: restore stage order ----------------------
    async def assemble_plan_node(state: OverallState) -> dict:
        ordered = sorted(state["stage_plans"], key=lambda s: s.stage_order)
        return {"ordered_stage_plans": ordered}

    # --- Phase 3 fan-out: one content-generation call per stage, in parallel
    def fan_out_to_stage_generation(state: OverallState) -> List[Send]:
        ordered = state["ordered_stage_plans"]
        sends = []
        for stage_plan in ordered:
            prev_stages = [
                {"name": s.stage_name, "description": s.stage_description}
                for s in ordered if s.stage_order < stage_plan.stage_order
            ]
            next_stages = [
                {"name": s.stage_name, "description": s.stage_description}
                for s in ordered if s.stage_order > stage_plan.stage_order
            ]
            sends.append(Send("generate_stage", {
                "stage_plan": stage_plan,
                "interview_focus": state["interview_focus"],
                "prev_stages": prev_stages,
                "next_stages": next_stages,
            }))
        return sends

    async def generate_stage_node(state: StageContentWorkerState) -> dict:
        stage_plan = state["stage_plan"]
        generated_content = await stage_chain.invoke(
            stage_plan=stage_plan,
            interview_focus=state["interview_focus"],
            prev_stages=state["prev_stages"],
            next_stages=state["next_stages"],
        )
        merged_stage = StageBase(
            stage_order=stage_plan.stage_order,
            stage_name=stage_plan.stage_name,
            stage_description=stage_plan.stage_description,
            interviewer_persona=generated_content.interviewer_persona,
            questions_and_answers=generated_content.questions_and_answers,
        )
        return {"generated_stages": [merged_stage]}

    # --- Final join: restore stage order for the response -------------------
    async def finalize_node(state: OverallState) -> dict:
        ordered = sorted(state["generated_stages"], key=lambda s: s.stage_order)
        print(f"Final Interview Pipeline: {ordered}")
        return {"final_pipeline": ordered}

    graph = StateGraph(OverallState)
    graph.add_node("plan_stages", plan_stages_node)
    graph.add_node("extract_cv_context", extract_cv_context_node)
    graph.add_node("assemble_plan", assemble_plan_node)
    graph.add_node("generate_stage", generate_stage_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "plan_stages")
    graph.add_conditional_edges("plan_stages", fan_out_to_cv_context, ["extract_cv_context"])
    graph.add_edge("extract_cv_context", "assemble_plan")
    graph.add_conditional_edges("assemble_plan", fan_out_to_stage_generation, ["generate_stage"])
    graph.add_edge("generate_stage", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Thin orchestrator wrapper, mirrors the previous class's public interface
# ---------------------------------------------------------------------------

class InterviewOrchestrator:
    def __init__(self, planner_llm: Runnable, cv_context_llm: Runnable, stage_llm: Runnable):
        self.app = build_interview_graph(planner_llm, cv_context_llm, stage_llm)

    async def run_pipeline(
        self, cv_text: str, jd_text: str, company_info: str, additional_notes: str
    ) -> List[StageBase]:
        result = await self.app.ainvoke({
            "cv_text": cv_text,
            "jd_text": jd_text,
            "company_info": company_info,
            "additional_notes": additional_notes,
            "interview_focus": [],
            "stage_skeletons": [],
            "stage_plans": [],
            "ordered_stage_plans": [],
            "generated_stages": [],
            "final_pipeline": [],
        })
        return result["final_pipeline"]