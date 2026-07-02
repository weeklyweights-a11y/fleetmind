import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, connection_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[connection_id] = websocket

    async def disconnect(self, connection_id: str) -> None:
        async with self._lock:
            self._connections.pop(connection_id, None)

    async def send_json(self, connection_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            websocket = self._connections.get(connection_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.exception("Failed to send WS message to %s", connection_id)

    async def broadcast(self, connection_ids: list[str], payload: dict[str, Any]) -> None:
        await asyncio.gather(
            *(self.send_json(connection_id, payload) for connection_id in connection_ids)
        )


ws_manager = WebSocketManager()
