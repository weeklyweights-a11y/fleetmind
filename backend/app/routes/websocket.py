import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.chat.conversation_summary import generate_conversation_summary
from app.chat.orchestrator import run_chat_turn
from app.chat.session import (
    create_conversation,
    end_conversation,
    init_chat_session,
    resume_conversation,
    touch_session_activity,
)
from app.config import settings
from app.database import async_session_factory
from app.redis_client import delete_ws_subscription, get_chat_session, merge_ws_subscriptions
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_active_conversations: dict[str, str] = {}


def _parse_idle_seconds(session: dict | None) -> float | None:
    if not session:
        return None
    turn = session.get("turn_state") or {}
    last = turn.get("last_activity_at") or session.get("last_activity_at")
    if not last:
        return None
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt).total_seconds()
    except ValueError:
        return None


async def _handle_chat_start(websocket: WebSocket, message: dict, connection_id: str) -> None:
    operator_name = message.get("operator_name") or "default"
    requested_id = message.get("conversation_id")

    async with async_session_factory() as db:
        resumed = False
        conversation_id: uuid.UUID
        if requested_id:
            try:
                cid = uuid.UUID(str(requested_id))
            except ValueError:
                cid = None  # type: ignore
            if cid and await resume_conversation(db, cid):
                conversation_id = cid
                resumed = True
            else:
                conversation_id = await create_conversation(db, operator_name)
                await init_chat_session(db, conversation_id, operator_name)
        else:
            conversation_id = await create_conversation(db, operator_name)
            await init_chat_session(db, conversation_id, operator_name)
        await db.commit()

    _active_conversations[connection_id] = str(conversation_id)
    await websocket.send_json(
        {
            "type": "chat_started",
            "conversation_id": str(conversation_id),
            "resumed": resumed,
        }
    )


async def _handle_chat_end(connection_id: str, conversation_id: str | None) -> None:
    if not conversation_id:
        conversation_id = _active_conversations.get(connection_id)
    if not conversation_id:
        return
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        return

    async with async_session_factory() as db:
        row = await end_conversation(db, cid)
        await db.commit()
        if row and row.ended_at:
            asyncio.create_task(generate_conversation_summary(cid))
    _active_conversations.pop(connection_id, None)


async def _handle_chat_message(websocket: WebSocket, message: dict, connection_id: str) -> None:
    conversation_id = message.get("conversation_id") or _active_conversations.get(connection_id)
    content = (message.get("content") or "").strip()
    if not conversation_id or not content:
        await websocket.send_json({"type": "error", "message": "Missing conversation_id or content"})
        return

    session = await get_chat_session(str(conversation_id))
    idle = _parse_idle_seconds(session)
    if idle is not None and idle > settings.chat_idle_timeout_seconds:
        await _handle_chat_end(connection_id, str(conversation_id))
        await websocket.send_json({"type": "error", "message": "Conversation timed out. Please start a new chat."})
        return

    await touch_session_activity(str(conversation_id))

    async def send_fn(payload: dict) -> None:
        await websocket.send_json(payload)

    try:
        await run_chat_turn(
            content,
            str(conversation_id),
            message.get("operator_name") or "default",
            message.get("dashboard_context"),
            send_fn,
        )
    except Exception as exc:
        logger.exception("Chat turn failed for %s", conversation_id)
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Chat processing failed: {exc}",
                "conversation_id": str(conversation_id),
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

            elif msg_type == "chat_start":
                await _handle_chat_start(websocket, message, connection_id)

            elif msg_type == "chat_message":
                await _handle_chat_message(websocket, message, connection_id)

            elif msg_type == "chat_end":
                await _handle_chat_end(connection_id, message.get("conversation_id"))

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", connection_id)
    finally:
        await _handle_chat_end(connection_id, _active_conversations.get(connection_id))
        await delete_ws_subscription(connection_id)
        await ws_manager.disconnect(connection_id)
        _active_conversations.pop(connection_id, None)
