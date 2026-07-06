"""LLM Call 1: query understanding."""

from __future__ import annotations

import json
from typing import Any

from app.chat import intents
from app.chat.prompts import load_prompt
from app.chat.schemas import (
    ChatGraphState,
    DashboardContext,
    DispatchPlanItem,
    EntityRef,
    QueryUnderstanding,
    TimeScope,
    TurnState,
)
from app.config import settings
from app.services.gemini_client import generate_json


def _prompt_turn_history(turn_state: TurnState, limit: int | None = None) -> str:
    limit = limit or settings.chat_turn_history_prompt_limit
    entries = turn_state.turn_history[-limit:]
    return json.dumps([e.model_dump(mode="json") for e in entries], indent=2)


def build_understanding_prompt(state: ChatGraphState) -> str:
    base = load_prompt("query_understanding.txt")
    turn_state = state.get("conversation_context") or TurnState()
    profile = state.get("operator_profile")
    dashboard = state.get("dashboard_context") or DashboardContext()
    summaries = state.get("recent_summaries") or turn_state.recent_summaries or []

    blocks = [
        base,
        f"Operator message: {state.get('message', '')}",
        f"Current entity: {turn_state.current_entity.model_dump(mode='json') if turn_state.current_entity else None}",
        f"Current time window: {turn_state.current_time_window.model_dump(mode='json') if turn_state.current_time_window else None}",
        f"Current topic carryover: {turn_state.current_topic}",
        f"Current intent carryover: {turn_state.current_intent}",
        f"Recent turn history (last {settings.chat_turn_history_prompt_limit}): {_prompt_turn_history(turn_state)}",
        f"Dashboard context: {dashboard.model_dump(mode='json')}",
        f"Operator profile: {profile.model_dump(mode='json') if profile else {}}",
        f"Recent conversation summaries: {json.dumps(summaries[:5], indent=2)}",
    ]
    return "\n\n".join(blocks)


def _coerce_understanding(data: dict[str, Any]) -> QueryUnderstanding:
    entities = []
    for e in data.get("entities") or []:
        if isinstance(e, dict):
            entities.append(EntityRef(**e))
    ts_raw = data.get("time_scope") or {}
    time_scope = TimeScope(**ts_raw) if isinstance(ts_raw, dict) else None
    plan = []
    for p in data.get("dispatch_plan") or []:
        if isinstance(p, dict) and p.get("function"):
            plan.append(DispatchPlanItem(function=str(p["function"]), params=p.get("params") or {}))
    intent = str(data.get("intent") or intents.ENTITY_OVERVIEW)
    if intent not in intents.ALL_INTENTS:
        intent = intents.ENTITY_OVERVIEW
    confidence = float(data.get("confidence", 0.8))
    return QueryUnderstanding(
        entities=entities,
        time_scope=time_scope,
        intent=intent,
        dispatch_plan=plan,
        response_guidance=str(data.get("response_guidance") or ""),
        confidence=confidence,
    )


async def understand_query(state: ChatGraphState) -> QueryUnderstanding:
    prompt = build_understanding_prompt(state)
    try:
        raw = await generate_json(prompt)
        return _coerce_understanding(raw if isinstance(raw, dict) else {})
    except Exception:
        return QueryUnderstanding(confidence=0.0, response_guidance="Ask a clarifying question.")
