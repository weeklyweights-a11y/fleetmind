"""Clarifying question generation (LLM Call 2 on clarify path)."""

from __future__ import annotations

from app.chat.prompts import load_prompt
from app.chat.schemas import ChatGraphState
from app.chat.streaming import WsStreamCallback
from app.services.gemini_client import generate_text, stream_text


def build_clarify_prompt(state: ChatGraphState) -> str:
    base = load_prompt("clarify.txt")
    qu = state.get("query_understanding")
    return (
        f"{base}\n\nOperator message: {state.get('message', '')}\n"
        f"Partial understanding: {qu.model_dump(mode='json') if qu else {}}"
    )


async def clarify_and_stream(state: ChatGraphState, callback: WsStreamCallback) -> str:
    prompt = build_clarify_prompt(state)
    buffer = ""
    try:
        async for delta in stream_text(prompt):
            buffer += delta
            await callback.send_delta(delta)
    except Exception:
        text = await generate_text(prompt)
        buffer = text
        await callback.send_delta(text)
    return buffer.strip() or "Which truck or topic did you mean?"
