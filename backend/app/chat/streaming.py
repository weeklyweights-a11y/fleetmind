"""WebSocket streaming helpers."""

from __future__ import annotations

from typing import Any, Callable


class WsStreamCallback:
    def __init__(self, send_fn: Callable[[dict[str, Any]], Any], conversation_id: str):
        self._send = send_fn
        self.conversation_id = conversation_id

    async def send_delta(self, content: str) -> None:
        if not content:
            return
        await self._send(
            {
                "type": "chat_response",
                "conversation_id": self.conversation_id,
                "content": content,
                "streaming": True,
                "done": False,
            }
        )

    async def send_done(self, tools_used: list[dict[str, Any]] | None = None) -> None:
        payload: dict[str, Any] = {
            "type": "chat_response",
            "conversation_id": self.conversation_id,
            "content": "",
            "streaming": False,
            "done": True,
        }
        if tools_used is not None:
            payload["tools_used"] = tools_used
        await self._send(payload)
