from fastapi import WebSocket
from typing import Any, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # session_id -> WebSocket
        self.connections: dict[int, WebSocket] = {}
        # session_id -> asyncio.Queue (for buffering messages before connection)
        self.message_queues: dict[int, asyncio.Queue] = {}
        # session_id -> bool (connection state)
        self.connected: set[int] = set()

    async def connect(self, session_id: int, websocket: WebSocket) -> None:
        """Accept WebSocket and flush any buffered messages."""
        await websocket.accept()
        self.connections[session_id] = websocket
        self.connected.add(session_id)
        
        # Flush any buffered messages sent before connection
        if session_id in self.message_queues:
            queue = self.message_queues[session_id]
            while not queue.empty():
                data = await queue.get()
                try:
                    await websocket.send_json(data)
                except Exception as e:
                    logger.error(f"Failed to send buffered message: {e}")
            del self.message_queues[session_id]
        
        logger.info(f"WebSocket connected for session {session_id}")

    def disconnect(self, session_id: int) -> None:
        """Remove connection and cleanup."""
        self.connections.pop(session_id, None)
        self.connected.discard(session_id)
        self.message_queues.pop(session_id, None)
        logger.info(f"WebSocket disconnected for session {session_id}")

    async def send(self, session_id: int, data: dict) -> bool:
        """
        Send message to WebSocket.
        Returns True if sent successfully, False otherwise.
        Buffers message if not yet connected.
        """
        if session_id in self.connected:
            websocket = self.connections.get(session_id)
            if websocket:
                try:
                    await websocket.send_json(data)
                    return True
                except Exception as e:
                    logger.error(f"Failed to send to session {session_id}: {e}")
                    self.disconnect(session_id)
                    return False
        else:
            # Buffer message for later delivery
            if session_id not in self.message_queues:
                self.message_queues[session_id] = asyncio.Queue(maxsize=100)
            
            try:
                self.message_queues[session_id].put_nowait(data)
                logger.debug(f"Buffered message for session {session_id}")
                return True
            except asyncio.QueueFull:
                logger.warning(f"Message queue full for session {session_id}")
                return False
        
        return False

    async def send_error(self, session_id: int, error: str, detail: str = "") -> bool:
        """Send an error message through WebSocket."""
        return await self.send(session_id, {
            "type": "error",
            "error": error,
            "detail": detail,
        })

    async def send_progress(self, session_id: int, step: str, progress: int) -> bool:
        """Send a progress update through WebSocket."""
        return await self.send(session_id, {
            "type": "progress",
            "step": step,
            "progress": min(100, max(0, progress)),  # Clamp to 0-100
        })

    def is_connected(self, session_id: int) -> bool:
        """Check if a session has an active WebSocket connection."""
        return session_id in self.connected


# Singleton instance
manager = ConnectionManager()