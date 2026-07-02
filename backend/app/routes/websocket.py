import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.redis_client import delete_ws_subscription, merge_ws_subscriptions
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


async def _mock_chat_stream(websocket: WebSocket, conversation_id: str, user_text: str) -> None:
    reply = f"Chat agent arrives in Phase 5. You asked: {user_text}"
    words = reply.split(" ")
    buffer = ""
    for word in words:
        buffer = f"{buffer} {word}".strip()
        await websocket.send_json(
            {
                "type": "chat_response",
                "conversation_id": conversation_id,
                "content": buffer,
                "streaming": True,
                "done": False,
            }
        )
        await asyncio.sleep(0.05)
    await websocket.send_json(
        {
            "type": "chat_response",
            "conversation_id": conversation_id,
            "content": reply,
            "streaming": False,
            "done": True,
        }
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    connection_id = str(uuid.uuid4())
    await ws_manager.connect(connection_id, websocket)
    await merge_ws_subscriptions(connection_id, [], [])

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
                unsubscribe = message.get("unsubscribe", [])
                updated = await merge_ws_subscriptions(connection_id, topics, unsubscribe)
                await websocket.send_json({"type": "subscribed", "topics": updated})

            elif msg_type == "unsubscribe":
                topics_to_remove = message.get("topics", [])
                updated = await merge_ws_subscriptions(connection_id, [], topics_to_remove)
                await websocket.send_json({"type": "unsubscribed", "topics": updated})

            elif msg_type == "chat_message":
                conversation_id = message.get("conversation_id") or str(uuid.uuid4())
                content = message.get("content", "")
                await _mock_chat_stream(websocket, conversation_id, content)

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
