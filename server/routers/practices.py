import asyncio
from fastapi import APIRouter, HTTPException, status 
from loguru import logger

from daily_utils import create_daily_room, create_daily_token, delete_daily_room
# from bot_daily import run_bot_entrypoint
from bot_daily_flow import run_bot_entrypoint
from auth import CurrentUser 
import crud
from database import DBSession
from schemas import PracticeResponse

active_bots = {}  # room_url -> task

router = APIRouter()

@router.get("/{practice_attempt_id}", response_model=PracticeResponse)
async def start_bot(  
    practice_attempt_id: int,
    db: DBSession,
    currentUser: CurrentUser,
    ):
    
    practice_attempt = await crud.get_practice_attempt(db, practice_attempt_id)
    
    if not practice_attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"practice attempt with ID {practice_attempt} does not exist.",
        )
    
    if not crud.practice_attempt_own_by(currentUser.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to get Practice Attempt.",
        )
        
    return practice_attempt 


@router.post("/{stage_id}", response_model=PracticeResponse)
async def start_bot( 
    stage_id: int,
    db: DBSession,
    currentUser: CurrentUser,
    ):
    stage = await crud.get_stage(
        db,
        stage_id,
    )
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"stage with ID {stage} does not exist.",
        )
    
    if not await crud.stage_owned_by(
                    db,
                    stage_id,
                    currentUser.id,
                ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create Practice Attempt using stage.",
        )
        
    room = await create_daily_room()
    room_url = room["url"]
    logger.info(f"Created room: {room_url}")
    token = await create_daily_token(room["name"])
    
    practice_attempt = await crud.create_practice_attempt(
        db,
        stage_id,
        room_url,
        token,
        "STARTED",
    )    
    task = asyncio.create_task(
        run_bot_entrypoint(
            room_url=room_url,
            token=token, 
            stage_id=stage_id,
            practice_attempt_id=practice_attempt.id        
            )
    )
    active_bots[room_url] = task
    return practice_attempt


@router.post("/stop/{practice_attempt_id}")
async def stop_bot(
    practice_attempt_id: int,
    db: DBSession,
    currentUser: CurrentUser,
    ):
    practice_attempt = await crud.get_practice_attempt(db, practice_attempt_id)
    
    if not practice_attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"practice attempt with ID {practice_attempt} does not exist.",
        )
    
    if not (await crud.practice_attempt_owned_by(db, practice_attempt_id, currentUser.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to stop Practice Attempt.",
        )
        
    practice_attempt = await crud.stop_practice_attempt(db, practice_attempt_id)
    active_bots.pop(practice_attempt.room_url).cancel()
    await delete_daily_room(practice_attempt.room_url)
    return {"status": "stopped"}

