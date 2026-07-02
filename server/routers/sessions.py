from asyncio import subprocess
import os
import sys
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status, Depends
import httpx
from auth import CurrentUser
from sqlalchemy import select 
import models
from database import DBSession
import crud, schemas
from settings import settings
from services import create_interview_session_service
from ws_connection_manager import manager

router = APIRouter()

@router.post(
    "",
    response_model=schemas.SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview_session(
    current_user: CurrentUser ,
    db: DBSession ,
    cv: UploadFile = File(...),
    job_description: str = Form(...),
    company_info: str = Form(...),
    additional_info: str = Form(...),
    
):
    session_input = schemas.SessionCreate(
        job_description=job_description,
        company_info=company_info,
        additional_info=additional_info,
    )

    new_session = await crud.create_session(
        db=db,
        session_data=session_input,
        cv=cv,
        user_id=current_user.id,
    )

    return new_session

@router.get(
    "",
    response_model=list[schemas.SessionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_user_sessions(current_user: CurrentUser, db: DBSession):
    sessions = await crud.get_sessions(db=db, user_id=current_user.id)
    return sessions


@router.get(
    "/{session_id}",
    response_model=schemas.SessionPublic,
    status_code=status.HTTP_200_OK,
)
async def get_interview_session(
    session_id: int, current_user: CurrentUser, db: DBSession
):

    session = await crud.get_session(
        db=db,
        session_id=session_id,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )
        
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this session.",
        )
    
    return session



@router.post(
    "/{session_id}/stages",
    response_model=schemas.InterviewPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_interview_plan(
    session_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    # Validate session exists
    session = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    session = session.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {session_id} does not exist.",
        )
    
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to generate a plan for this session.",
        )

    try:
        generated_blueprint = await create_interview_session_service(session)
    except Exception as e:
        # Notify WebSocket about the error
        await manager.send_error(
            session_id,
            error="generation_failed",
            detail=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate interview plan: {str(e)}"
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
    "/{session_id}/stages",
    response_model=schemas.InterviewPlanResponse,
    status_code=status.HTTP_200_OK,
)
async def get_interview_plan(session_id: int, current_user: CurrentUser, db: DBSession):
    session = await crud.get_session(db=db, session_id=session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {session_id} does not exist.",
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access the plan for this session.",
        )

    stages = await crud.get_interview_stages(db=db, session_id=session_id)

    return schemas.InterviewPlanResponse(session_id=session_id, stages=stages)

 

@router.patch(
    "/{session_id}/feedback",
    response_model=schemas.SessionEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit wrap-up feedback to initiate Version 2 structural shifts",
)
def submit_session_feedback(
    session_id: int, payload: schemas.SessionFeedbackUpdate, db: DBSession
):
    """
    Updates the parent interview session configuration framework with core user feedback.
    The next time they call `/sessions/{session_id}/generate-plan` (Step 3), the AI worker
    will read this feedback field to generate tailored V2 Stages.
    """
    # 1. Commit modifications to SQLite
    updated_session = crud.update_session_feedback(
        db, session_id=session_id, feedback_data=payload
    )
    if not updated_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview Session setup {session_id} not found.",
        )

    # 2. Extract historical execution metrics for context analytics
    attempt_count = crud.get_practice_runs_count(db, session_id=session_id)

    # 3. Assemble full structure response
    return schemas.SessionEvaluationResponse(
        id=updated_session.id,
        user_id=updated_session.user_id,
        feedback=updated_session.feedback,
        date_created=updated_session.date_created,
        total_practice_runs=attempt_count,
    )
