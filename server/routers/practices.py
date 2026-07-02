# main.py
import os
import asyncio
import httpx
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger
import time 

from bot_daily import run_bot_entrypoint
from auth import CurrentUser
from schemas import StartPracticeRequest, StartPracticeResponse, StopPracticeRequest
import crud
from database import DBSession
from settings import settings

active_bots = {}  # room_url -> task




router = APIRouter()

async def create_daily_token(room_name: str, is_owner: bool = True) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.DAILY_API_URL}/meeting-tokens",
            headers={
                "Authorization": f"Bearer {settings.DAILY_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "room_name": room_name,
                    "is_owner": is_owner,
                    "exp": int(time.time()) + 3600,
                }
            }
        )
        response.raise_for_status()
        return response.json()["token"]
    
async def create_daily_room() -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.DAILY_API_URL}/rooms",
            headers={
                "Authorization": f"Bearer {settings.DAILY_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "enable_prejoin_ui": False,
                    "enable_screenshare": False,
                    "enable_chat": False,
                    "start_video_off": True,
                    "start_audio_off": False,
                    "exp": int(time.time()) + 3600 ,
                }
            }
        )
        response.raise_for_status()
        return response.json()


async def delete_daily_room(room_url: str):
    room_name = room_url.split("/")[-1]
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(
                f"{settings.DAILY_API_URL}/rooms/{room_name}",
                headers={"Authorization": f"Bearer {settings.DAILY_API_KEY}"}
            )
        except Exception as e:
            logger.warning(f"Failed to delete room: {e}")


@router.post("/start", response_model=StartPracticeResponse)
async def start_bot(
    request: StartPracticeRequest,
    currentUser: CurrentUser,
    ):
    try:
        room = await create_daily_room()
        room_url = room["url"]
        logger.info(f"Created room: {room_url}")
        token = await create_daily_token(room["name"])
        
        task = asyncio.create_task(
            run_bot_entrypoint(
                room_url=room_url,
                token=token, 
                stage_id=request.stage_id,
                practice_session_id=request.practice_session_id
            )
        )
        active_bots[room_url] = task
        
        return StartPracticeResponse(
            practice_session_id=request.practice_session_id,
            stage_id=request.stage_id,
            room_url= room_url,
            token= token,  
        )
    except Exception as e:
        logger.error(f"Start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_bot(
    request: StopPracticeRequest,
    currentUser: CurrentUser,
    ):
    room_url = request.room_url
    if room_url and room_url in active_bots:
        active_bots.pop(room_url).cancel()
    await delete_daily_room(room_url)
    return {"status": "stopped"}



@router.post("")
async def create_practice_session(
    session_id: int,
    current_user: CurrentUser,
    db: DBSession
):
    session = await crud.get_session(db=db, session_id=session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {session_id} does not exist.",
        )
    
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to create a practice session for this session.",
        )

    practice_session = await crud.create_practice_session(db=db, session_id=session_id)
    
    return {"practice_session_id": practice_session.id}



