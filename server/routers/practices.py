from typing import Annotated
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile
from schemas import PostResponse, UserUpdate
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import PostResponse, UserCreate, UserPrivate, UserPublic, Token
import models
from database import get_db

from datetime import timedelta
from fastapi.security import OAuth2PasswordRequestForm
from auth import CurrentUser, create_access_token, hash_password, verify_password
from PIL import UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from image_utils import delete_profile_image, process_profile_image
from config import settings

router = APIRouter()

@router.post(
    "/practices/{practice_stage_id}/answers",
    response_model=schemas.AnswerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Web-hook stream logger used by Pipecat background pipeline context tools"
)
def log_streamed_answer(practice_stage_id: int, answer_input: schemas.AnswerCreate, db: DBSession = Depends(get_db)):
    """
    This endpoint can be called securely by your Pipecat server process (using custom tools) 
    every time a question finishes, logging the transcription and metrics in real-time.
    """
    # Confirm valid destination block
    stage_exists = db.query(models.PracticeStage).filter(models.PracticeStage.id == practice_stage_id).first()
    if not stage_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target running context not found.")
        
    return crud.record_live_answer(db=db, practice_stage_id=practice_stage_id, answer_data=answer_input)