import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from ws_connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int):
    await manager.connect(session_id, websocket)
    
    try:
        # Send immediate connection confirmation
        await manager.send(session_id, {
            "type": "connected",
            "message": "WebSocket connection established"
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            
            # Handle ping/heartbeat from client
            if data == "ping":
                await websocket.send_text("pong")
            # Could add other message types here (e.g., cancel operation)
            
    except WebSocketDisconnect:
        logger.info(f"Client disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
    finally:
        manager.disconnect(session_id)