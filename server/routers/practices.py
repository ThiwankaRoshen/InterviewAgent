from fastapi import APIRouter, HTTPException, status, Depends
import models
from database import DBSession
from server import crud
from server.schemas import AnswerCreate, AnswerResponse

router = APIRouter()

@router.post(
    "/practices/{practice_stage_id}/answers",
    response_model=AnswerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Web-hook stream logger used by Pipecat background pipeline context tools"
)
def log_streamed_answer(practice_stage_id: int, answer_input: AnswerCreate, db: DBSession):
    """
    This endpoint can be called securely by your Pipecat server process (using custom tools) 
    every time a question finishes, logging the transcription and metrics in real-time.
    """
    # Confirm valid destination block
    stage_exists = db.query(models.PracticeStage).filter(models.PracticeStage.id == practice_stage_id).first()
    if not stage_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target running context not found.")
        
    return crud.record_live_answer(db=db, practice_stage_id=practice_stage_id, answer_data=answer_input)