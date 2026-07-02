from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader 
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough 
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json 
import fitz
from langsmith import traceable
from settings import settings

# ============================================
# PYDANTIC SCHEMAS FOR STRUCTURED OUTPUT
# ============================================

class SkillSet(BaseModel):
    """Skills grouped by category"""
    programming_languages: List[str] = Field(default_factory=list, description="Programming languages")
    frameworks: List[str] = Field(default_factory=list, description="Frameworks and libraries")
    databases: List[str] = Field(default_factory=list, description="Databases")
    cloud: List[str] = Field(default_factory=list, description="Cloud platforms and services")
    tools: List[str] = Field(default_factory=list, description="DevOps and other tools")
    soft_skills: List[str] = Field(default_factory=list, description="Soft skills")


class WorkExperience(BaseModel):
    """Single work experience entry"""
    company: str = Field(description="Company name")
    role: str = Field(description="Job title/role")
    duration: str = Field(description="Employment duration")
    highlights: List[str] = Field(default_factory=list, description="Key achievements")


class Education(BaseModel):
    """Education entry"""
    degree: str = Field(description="Degree obtained")
    institution: str = Field(description="University/college name")
    year: Optional[str] = Field(default=None, description="Graduation year")


class Project(BaseModel):
    """Project entry"""
    name: str = Field(description="Project name")
    description: str = Field(description="Brief description")
    technologies: List[str] = Field(default_factory=list, description="Technologies used")


class ParsedResume(BaseModel):
    """Complete parsed resume structure"""
    name: str = Field(description="Full name of candidate")
    email: str = Field(description="Email address")
    phone: Optional[str] = Field(default=None, description="Phone number")
    linkedin: Optional[str] = Field(default=None, description="LinkedIn profile URL")
    summary: str = Field(description="Professional summary")
    skills: SkillSet = Field(default_factory=SkillSet, description="All skills")
    work_experience: List[WorkExperience] = Field(default_factory=list, description="Work history")
    education: List[Education] = Field(default_factory=list, description="Education history")
    certifications: List[str] = Field(default_factory=list, description="Certifications")
    projects: List[Project] = Field(default_factory=list, description="Notable projects")
    total_experience_years: Optional[int] = Field(default=None, description="Estimated total years of experience")
    key_strengths: List[str] = Field(default_factory=list, description="Candidate's key strengths")


# ============================================
# RESUME PARSER CLASS
# ============================================

class LangChainResumeParser:
    """Parse resumes using only LangChain components"""
    
    def __init__(self,  temperature: float = 0):
        # self.llm = ChatOpenAI(
        #     base_url=settings.BASE_URL_INTERVIEW_GEN,
        #     model=settings.MODEL_INTERVIEW_GEN,
        #     temperature=temperature,
        #     api_key=settings.GITHUB_TOKEN_INTERVIEW_GEN,
        # ) 
        
        self.llm = ChatMistralAI(
            model=settings.MISTRAL_MODEL,
            temperature=0,
            max_retries=2,
            mistral_api_key=settings.MISTRAL_API_KEY
        )
        
        self.resume_parser = PydanticOutputParser(pydantic_object=ParsedResume)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert resume parser. Extract all information accurately from the resume.
            
            {format_instructions}
            
            Rules:
            - Be thorough and accurate
            - Don't invent information not present in resume
            - Normalize skill names (e.g., "JS" -> "JavaScript")
            - Estimate experience years if not explicitly stated
            """),
            ("human", "Parse this resume:\n\n{resume_text}")
        ])
        
        self.chain = (
            {"resume_text": RunnablePassthrough(), 
             "format_instructions": lambda _: self.resume_parser.get_format_instructions()}
            | self.prompt
            | self.llm
            | self.resume_parser
        )
    
    def load_pdf(self, path: str) -> str:
        """Load PDF using LangChain document loader"""
        loader = PyPDFLoader(path)
        docs = loader.load()
        return "\n\n".join([doc.page_content for doc in docs])
    
    def parse(self, pdf_path: str) -> ParsedResume:
        """Parse resume from PDF path"""
        text = self.load_pdf(pdf_path)
        return self.chain.invoke(text)
    
    def parse_text(self, text: str) -> ParsedResume:
        """Parse resume from text"""
        return self.chain.invoke(text)






@traceable(name="PyMuPDF Resume Parser")
def parse_using_pymupdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text = ""

    for page in doc:
        text += page.get_text()

    return text

# # parsed_resume = parse_using_pymupdf("media/cv_files/0470b3ff7cc94f09877c7ae2e8e56ed4.pdf")
# parser = LangChainResumeParser()

# parsed_resume = parser.parse("media/cv_files/0470b3ff7cc94f09877c7ae2e8e56ed4.pdf")
# print(parsed_resume)