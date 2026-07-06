"""WebSocket chat handler tests with mocked orchestrator."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.routes import websocket as ws_mod


@pytest.fixture
def mock_chat_turn(monkeypatch):
    calls: list[dict] = []

    async def fake_run(message, conversation_id, operator_name, dashboard_context, ws_send_fn):
        calls.append(
            {
                "message": message,
                "conversation_id": conversation_id,
                "operator_name": operator_name,
                "dashboard_context": dashboard_context,
            }
        )
        await ws_send_fn(
            {
                "type": "chat_response",
                "conversation_id": conversation_id,
                "content": "Hello ",
                "streaming": True,
                "done": False,
            }
        )
        await ws_send_fn(
            {
                "type": "chat_response",
                "conversation_id": conversation_id,
                "content": "world",
                "streaming": True,
                "done": False,
            }
        )
        await ws_send_fn(
            {
                "type": "chat_response",
                "conversation_id": conversation_id,
                "content": "",
                "streaming": False,
                "done": True,
                "tools_used": [
                    {"function": "get_fleet_overview", "params": {}, "status": "ok", "result_summary": "ok"}
                ],
            }
        )

    monkeypatch.setattr(ws_mod, "run_chat_turn", fake_run)
    return calls


@pytest.mark.asyncio
async def test_chat_start_returns_conversation_id(monkeypatch):
    cid = uuid.uuid4()
    monkeypatch.setattr(ws_mod, "create_conversation", AsyncMock(return_value=cid))
    monkeypatch.setattr(ws_mod, "init_chat_session", AsyncMock())
    monkeypatch.setattr(ws_mod, "resume_conversation", AsyncMock(return_value=False))

    websocket = AsyncMock()
    connection_id = "conn-1"
    await ws_mod._handle_chat_start(websocket, {"operator_name": "default"}, connection_id)

    websocket.send_json.assert_awaited_once()
    payload = websocket.send_json.await_args.args[0]
    assert payload["type"] == "chat_started"
    assert payload["conversation_id"] == str(cid)


@pytest.mark.asyncio
async def test_chat_message_invokes_orchestrator(mock_chat_turn, monkeypatch):
    sent: list[dict] = []

    async def capture(payload: dict) -> None:
        sent.append(payload)

    websocket = AsyncMock()
    websocket.send_json = capture
    connection_id = "conn-2"
    conversation_id = str(uuid.uuid4())
    ws_mod._active_conversations[connection_id] = conversation_id

    monkeypatch.setattr(ws_mod, "get_chat_session", AsyncMock(return_value={"last_activity_at": None}))
    monkeypatch.setattr(ws_mod, "touch_session_activity", AsyncMock())

    await ws_mod._handle_chat_message(
        websocket,
        {
            "conversation_id": conversation_id,
            "operator_name": "default",
            "content": "How is the fleet?",
            "dashboard_context": {"current_page": "/"},
        },
        connection_id,
    )

    assert len(mock_chat_turn) == 1
    assert mock_chat_turn[0]["message"] == "How is the fleet?"
    assert "".join(m["content"] for m in sent if m.get("streaming") and not m.get("done")) == "Hello world"
    assert sent[-1]["done"] is True
    assert sent[-1]["tools_used"][0]["function"] == "get_fleet_overview"


@pytest.mark.asyncio
async def test_chat_message_rejects_empty_content():
    websocket = AsyncMock()
    await ws_mod._handle_chat_message(
        websocket,
        {"conversation_id": str(uuid.uuid4()), "content": "   "},
        "conn-3",
    )
    websocket.send_json.assert_awaited()
    assert websocket.send_json.await_args.args[0]["type"] == "error"
