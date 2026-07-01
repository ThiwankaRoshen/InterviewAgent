from fastapi import APIRouter, HTTPException, status, Depends
import models
from database import DBSession
from server import crud
from server.schemas import AnswerCreate, AnswerResponse
import asyncio
from fastapi import FastAPI, Request, Depends
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection

from database import async_session_factory, get_db  # your existing setup
from bot import run_bot_entrypoint
router = APIRouter()
pcs_map: dict[str, SmallWebRTCConnection] = {}
background_tasks: set[asyncio.Task] = set()  # keep strong refs so tasks aren't GC'd mid-flight

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

 

@router.post("/api/offer/{stage_id}/{practice_stage_id}")
async def offer(stage_id: int, practice_stage_id: int, request: Request):
    body = await request.json()
    pc_id = body.get("pc_id")

    if pc_id and pc_id in pcs_map:
        connection = pcs_map[pc_id]
        await connection.renegotiate(sdp=body["sdp"], type=body["type"])
    else:
        connection = SmallWebRTCConnection(ice_servers=[])
        await connection.initialize(sdp=body["sdp"], type=body["type"])

        @connection.event_handler("closed")
        async def on_closed(conn):
            pcs_map.pop(conn.pc_id, None)

        # Launch the bot pipeline in the background — do NOT await it here,
        # or the HTTP response (SDP answer) never gets sent back to the client.
        task = asyncio.create_task(
            run_bot_entrypoint(connection, stage_id, practice_stage_id)
        )
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    answer = connection.get_answer()
    pcs_map[answer["pc_id"]] = connection
    return answer