from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from datetime import datetime

class UserBase(BaseModel): 
    email: EmailStr = Field(max_length=120)
    
class UserCreate(UserBase):
    password: str = Field(min_length=8)
    
class UserPublic(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    
    id: int 
    
class UserPrivate(UserPublic):
    email: EmailStr
 
class UserUpdate(BaseModel):
    email: EmailStr | None = Field(default=None, max_length=120)   

class Token(BaseModel):
    access_token: str
    token_type: str



class SessionCreate(BaseModel): 
    job_description: str = Field(..., description="The target job description text")
    company_info: str = Field(..., description="Information about the target company")
    additional_info: str = Field(..., description="Past interview sessions context, rumors, or extra details")


class SessionResponse(BaseModel):
    id: int 
    date_created: datetime
    job_description: str = Field(..., description="The target job description text")
    company_info: str = Field(..., description="Information about the target company")
    additional_info: str = Field(..., description="Past interview sessions context, rumors, or extra details")

    model_config = ConfigDict(from_attributes=True)
    
class StagePublic(BaseModel):
    stage_order: int = Field(..., description="The sequential order of the interview stage (e.g., 1, 2, 3)")
    stage_name: str = Field(..., description="Name of the stage (e.g., Technical, Behavioral)")
    stage_description: str = Field(..., description="What this specific stage evaluates")
    
    model_config = ConfigDict(from_attributes=True)
    
class SessionPublic(BaseModel):
    id: int 
    date_created: datetime
    job_description: str = Field(..., description="The target job description text")
    company_info: str = Field(..., description="Information about the target company")
    additional_info: str = Field(..., description="Past interview sessions context, rumors, or extra details")
    stages: list[StagePublic] = Field(..., description="The stages associated with this session")
    
    model_config = ConfigDict(from_attributes=True)
    
    
class StageBase(BaseModel):
    stage_order: int = Field(..., description="The sequential order of the interview stage (e.g., 1, 2, 3)")
    stage_name: str = Field(..., description="Name of the stage (e.g., Technical, Behavioral)")
    stage_description: str = Field(..., description="What this specific stage evaluates")
    interviewer_persona: str = Field(..., description="The personality/tone of the AI interviewer")
    questions_and_answers: str = Field(..., description="JSON string containing structured generated Q&As")
    
    model_config = ConfigDict(from_attributes=True)


class StageResponse(StageBase):
    id: int
    session_id: int

    model_config = ConfigDict(from_attributes=True)


class InterviewPlanResponse(BaseModel):
    session_id: int
    stages: list[StageResponse]
    




class PracticeResponse(BaseModel):
    id: int
    room_url: str
    token: str
    status: str
    md_results_path: str
    pdf_results_path: str

    model_config = ConfigDict(from_attributes=True)
