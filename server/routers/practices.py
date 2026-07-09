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
from dataclasses import dataclass

@dataclass
class BotSession:
    task: asyncio.Task
    stop_event: asyncio.Event

active_bots: dict[str, BotSession] = {}

# active_bots = {}  # room_url -> task

router = APIRouter()

@router.get("/{stage_id}", response_model=list[PracticeResponse])
async def start_bot(  
    stage_id: int,
    db: DBSession,
    currentUser: CurrentUser,
    ):
    
    practice_attempts = await crud.get_practice_attempts(db, stage_id)
    
    if not practice_attempts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"practice attempt with ID {stage_id} does not exist.",
        )
    
    if False in [await crud.practice_attempt_owned_by(db, practice_attempt.id, currentUser.id) 
                 for practice_attempt in practice_attempts] :
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to get Practice Attempt.",
        )
        
    return practice_attempts 


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
            detail=f"practice attempt with ID {practice_attempt_id} does not exist.",
        )
    
    if not await crud.practice_attempt_owned_by(db, practice_attempt_id, currentUser.id):
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
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        run_bot_entrypoint(
            room_url=room_url,
            token=token,
            stage_id=stage_id,
            practice_attempt_id=practice_attempt.id,
            stop_event=stop_event,
        )
    )
    active_bots[room_url] = BotSession(task=task, stop_event=stop_event)
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
    session = active_bots.pop(practice_attempt.room_url, None)

    if session:
        session.stop_event.set()
        try:
            # shield so our own timeout doesn't cancel the bot's cleanup task directly
            await asyncio.wait_for(asyncio.shield(session.task), timeout=60)
        except asyncio.TimeoutError:
            logger.warning(f"Bot for {practice_attempt.room_url} did not stop in time, force cancelling")
            session.task.cancel()
        except Exception:
            logger.exception("Bot task raised during graceful shutdown")

    await delete_daily_room(practice_attempt.room_url)
    return {"status": "stopped"}
