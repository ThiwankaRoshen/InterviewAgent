from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status, Depends
from auth import CurrentUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import models
from database import DBSession, get_db
import crud, schemas
from services import create_interview_session_service, mock_ai_generation_engine

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
    "/sessions/{session_id}/stages",
    response_model=schemas.InterviewPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_interview_plan(
    session_id: int, current_user: CurrentUser, db: DBSession
):
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

    generated_blueprint = await create_interview_session_service(session)

    saved_stages = await crud.create_interview_stages(
        db=db, session_id=session_id, generated_stages=generated_blueprint
    )

    return schemas.InterviewPlanResponse(session_id=session_id, stages=saved_stages)


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


@router.post(
    "/{session_id}/practice",
    response_model=schemas.StartPracticeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize DB session tracking data and fetch real-time Pipecat parameters",
)
async def start_practice_session(
    session_id: int, payload: schemas.StartPracticeRequest, db: DBSession
):
    """
    Called by the Web UI. It builds the row identifiers for this attempt, fetches
    the context to hand off to Pipecat, and returns the room tokens to the frontend client.
    """
    stage = await db.execute(
        select(models.Stage).where(
            models.Stage.id == payload.stage_id, models.Stage.session_id == session_id
        )
    )
    stage = stage.scalar_one()
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specified stage configuration mapping does not match this interview blueprint.",
        )

    p_session, p_stage = crud.initialize_practice_run(db, session_id=session_id)

    mock_room_url = f"https://your-app.daily.co/interview-room-{p_stage.id}"
    mock_token = f"jwt-token-for-stage-{p_stage.id}"

    return schemas.StartPracticeResponse(
        practice_session_id=p_session.id,
        practice_stage_id=p_stage.id,
        room_url=mock_room_url,
        token=mock_token,
    )


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
