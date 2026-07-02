import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.redis_client import delete_ws_subscription, get_ws_subscriptions, set_ws_subscriptions
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    connection_id = str(uuid.uuid4())
    await ws_manager.connect(connection_id, websocket)
    await set_ws_subscriptions(connection_id, [])

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = message.get("type")

            if msg_type == "subscribe":
                topics = message.get("topics", [])
                await set_ws_subscriptions(connection_id, topics)
                await websocket.send_json({"type": "subscribed", "topics": topics})

            elif msg_type == "unsubscribe":
                topics_to_remove = set(message.get("topics", []))
                current = await get_ws_subscriptions(connection_id)
                updated = [t for t in current if t not in topics_to_remove]
                await set_ws_subscriptions(connection_id, updated)
                await websocket.send_json({"type": "unsubscribed", "topics": updated})

            elif msg_type == "chat_message":
                await websocket.send_json(
                    {"type": "error", "message": "chat not available in Phase 1"}
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    finally:
        await delete_ws_subscription(connection_id)
        await ws_manager.disconnect(connection_id)
