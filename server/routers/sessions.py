from typing import Annotated
from fastapi import APIRouter, HTTPException, status, Depends
from auth import CurrentUser
from schemas import PostCreate, PostResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import PostCreate, PostResponse, PostUpdate
import models
from database import DBSession, get_db
from server import crud, schemas
from server.services import mock_ai_generation_engine

router = APIRouter()

@router.post(
    "/sessions", 
    response_model=schemas.SessionResponse, 
    status_code=status.HTTP_201_CREATED, 
)
def create_interview_session(
    session_input: schemas.SessionCreate, 
    current_user: CurrentUser,
    db: DBSession
): 
    
    try:
        new_session = crud.create_session(
            db=db, 
            session_data=session_input, 
            user_id=current_user.id
        )
        return new_session
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record session setup: {str(e)}"
        )
        
@router.get(
    "/sessions/{session_id}", 
    response_model=schemas.SessionResponse, 
    status_code=status.HTTP_201_CREATED, 
)
def create_interview_session(
    session_id: int, 
    current_user: CurrentUser,
    db: DBSession
): 

    session = crud.get_session(
        db=db, 
        session_id=session_id,  
    )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this session.",
        )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )
    return session 



@router.post(
    "/sessions/{session_id}/stages", 
    response_model=schemas.InterviewPlanResponse, 
    status_code=status.HTTP_201_CREATED, 
)
async def generate_interview_plan(
    session_id: int,
    current_user: CurrentUser,
    db: AsyncSession
): 
    session = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {session_id} does not exist."
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to generate a plan for this session."
        )

    generated_blueprint = mock_ai_generation_engine(
        job_description=session.job_description,
        company_info=session.company_info
    )
    
    saved_stages = await crud.create_interview_stages(
        db=db, 
        session_id=session_id, 
        generated_stages=generated_blueprint
    )
    
    return schemas.InterviewPlanResponse(
        session_id=session_id,
        stages=saved_stages
    )

@router.get(
    "/sessions/{session_id}/stages", 
    response_model=schemas.InterviewPlanResponse, 
    status_code=status.HTTP_200_OK, 
)
async def get_interview_plan(
    session_id: int,
    current_user: CurrentUser,
    db: AsyncSession
): 
    session = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {session_id} does not exist."
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access the plan for this session."
        )

    stages = await crud.get_interview_stages(db=db, session_id=session_id)
    
    return schemas.InterviewPlanResponse(
        session_id=session_id,
        stages=stages
    )
    


@router.post(
    "/sessions/{session_id}/practice", 
    response_model=schemas.StartPracticeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize DB session tracking data and fetch real-time Pipecat parameters"
)
def start_practice_session(session_id: int, payload: schemas.StartPracticeRequest, db: DBSession = Depends(get_db)):
    """
    Called by the Web UI. It builds the row identifiers for this attempt, fetches
    the context to hand off to Pipecat, and returns the room tokens to the frontend client.
    """
    # 1. Confirm session template and parent stages exist
    stage = db.query(models.Stage).filter(models.Stage.id == payload.stage_id, models.Stage.session_id == session_id).first()
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specified stage configuration mapping does not match this interview blueprint."
        )

    try:
        # 2. Track the physical instantiation row instances
        p_session, p_stage = crud.initialize_practice_run(db, session_id=session_id)
        
        # 3. Connect to Pipecat deployment orchestration layer here
        # (Mocking room tokens provided by Daily.co/WebRTC infrastructures used by Pipecat pipelines)
        mock_room_url = f"https://your-app.daily.co/interview-room-{p_stage.id}"
        mock_token = f"jwt-token-for-stage-{p_stage.id}"
        
        # Note: At this point, you typically trigger/spin up your Pipecat process 
        # passing `stage.interviewer_persona`, `stage.questions_and_answers`, and `p_stage.id`
        
        return schemas.StartPracticeResponse(
            practice_session_id=p_session.id,
            practice_stage_id=p_stage.id,
            room_url=mock_room_url,
            token=mock_token
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

import crud
import schemas
from database import get_db

app = FastAPI(title="Interview Prep AI Engine")


@app.patch(
    "/sessions/{session_id}/feedback", 
    response_model=schemas.SessionEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit wrap-up feedback to initiate Version 2 structural shifts"
)
def submit_session_feedback(
    session_id: int, 
    payload: schemas.SessionFeedbackUpdate, 
    db: DBSession 
):
    """
    Updates the parent interview session configuration framework with core user feedback.
    The next time they call `/sessions/{session_id}/generate-plan` (Step 3), the AI worker 
    will read this feedback field to generate tailored V2 Stages.
    """
    # 1. Commit modifications to SQLite
    updated_session = crud.update_session_feedback(db, session_id=session_id, feedback_data=payload)
    if not updated_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Interview Session setup {session_id} not found."
        )
        
    # 2. Extract historical execution metrics for context analytics
    attempt_count = crud.get_practice_runs_count(db, session_id=session_id)
    
    # 3. Assemble full structure response
    return schemas.SessionEvaluationResponse(
        id=updated_session.id,
        user_id=updated_session.user_id,
        feedback=updated_session.feedback,
        date_created=updated_session.date_created,
        total_practice_runs=attempt_count
    )