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
    cv: UploadFile = Field(..., description="The CV file to be uploaded")
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
    
    
class StageBase(BaseModel):
    stage_order: int = Field(..., description="The sequential order of the interview stage (e.g., 1, 2, 3)")
    stage_name: str = Field(..., description="Name of the stage (e.g., Technical, Behavioral)")
    stage_description: str = Field(..., description="What this specific stage evaluates")
    interviewer_persona: str = Field(..., description="The personality/tone of the AI interviewer")
    questions_and_answers: str = Field(..., description="JSON string containing structured generated Q&As")


class StageResponse(StageBase):
    id: int
    session_id: int

    model_config = ConfigDict(from_attributes=True)


class InterviewPlanResponse(BaseModel):
    session_id: int
    stages: list[StageResponse]
    


class StartPracticeRequest(BaseModel):
    stage_id: int = Field(..., description="The ID of the master Stage template being practiced")
    session_id: int = Field(..., description="The ID of the parent Session for this practice run")


class StartPracticeResponse(BaseModel):
    practice_session_id: int
    practice_stage_id: int
    # Pipecat/Daily connection details sent back to your frontend UI
    room_url: str = Field(..., description="The WebRTC/Daily URL for the front-end to connect to voice")
    token: str = Field(..., description="Access token for the voice room session")

    model_config = ConfigDict(from_attributes=True)


class AnswerCreate(BaseModel):
    question_order: int
    question_text: str
    behaviour: str = Field(..., description="Metrics from Pipecat like latency, interruption, confidence")
    answer_text: str = Field(..., description="The transcribed speech-to-text string")


class AnswerResponse(AnswerCreate):
    id: int
    practice_stage_id: int

    model_config = ConfigDict(from_attributes=True)
    
    
 
class SessionFeedbackUpdate(BaseModel):
    feedback: str = Field(
        ..., 
        description="User instructions for refining the track (e.g., 'Make technical stage focus more on system design')"
    )


class SessionEvaluationResponse(BaseModel):
    id: int
    user_id: int
    feedback: str
    date_created: datetime
    
    # We include a brief breakdown summary of previous historical attempts in the response
    total_practice_runs: int = Field(0, description="Count of how many times they practiced this setup")

    model_config = ConfigDict(from_attributes=True)