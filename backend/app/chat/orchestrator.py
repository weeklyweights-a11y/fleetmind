"""LangGraph orchestrator for chat turns."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from langgraph.graph import END, StateGraph

from app.chat.abbreviate_results import abbreviate_sub_agent_result
from app.chat.clarify import clarify_and_stream
from app.chat.dispatch import build_tools_used, execute_dispatch_plan
from app.chat.query_understanding import understand_query
from app.chat.response_synthesis import synthesize_and_stream
from app.chat.schemas import (
    ChatGraphState,
    CurrentEntity,
    DashboardContext,
    OperatorProfileSnapshot,
    TimeWindow,
    TurnHistoryEntry,
    TurnState,
    TurnStateUpdate,
)
from app.chat.session import append_message, load_turn_state, save_turn_state
from app.chat.streaming import WsStreamCallback
from app.config import settings
from app.database import async_session_factory

_turn_locks: dict[str, asyncio.Lock] = {}
_summary_scheduled: set[str] = set()


def _get_lock(conversation_id: str) -> asyncio.Lock:
    if conversation_id not in _turn_locks:
        _turn_locks[conversation_id] = asyncio.Lock()
    return _turn_locks[conversation_id]


async def load_context(state: ChatGraphState) -> ChatGraphState:
    turn_state = await load_turn_state(state["conversation_id"])
    async with async_session_factory() as db:
        from app.chat.proactive_context import load_proactive_alerts

        alerts = await load_proactive_alerts(db)
        turn_state.proactive_alerts = alerts
        await db.commit()
    session_raw = turn_state.model_dump(mode="json")
    state["conversation_context"] = turn_state
    state["proactive_alerts"] = alerts
    if not state.get("recent_summaries"):
        state["recent_summaries"] = turn_state.recent_summaries
    if not state.get("operator_profile"):
        data = await _load_profile_snapshot(state.get("operator_name", "default"))
        state["operator_profile"] = data
    return state


async def _load_profile_snapshot(operator_name: str) -> OperatorProfileSnapshot:
    from app.chat.session import load_operator_profile

    async with async_session_factory() as db:
        profile = await load_operator_profile(db, operator_name)
        await db.commit()
        return OperatorProfileSnapshot(
            operator_name=profile.operator_name,
            frequent_entities=profile.frequent_entities if isinstance(profile.frequent_entities, list) else [],
            frequent_topics=profile.frequent_topics if isinstance(profile.frequent_topics, list) else [],
            preferred_response_style=profile.preferred_response_style,
            query_preferences=profile.query_preferences if isinstance(profile.query_preferences, dict) else {},
            total_conversations=int(profile.total_conversations or 0),
        )


async def understand_query_node(state: ChatGraphState) -> ChatGraphState:
    from app.chat.dispatch_enrichment import enrich_query_understanding
    from app.chat.schemas import QueryUnderstanding

    try:
        qu = await understand_query(state)
        qu = await enrich_query_understanding(state, qu)
        state["query_understanding"] = qu
    except Exception:
        state["query_understanding"] = QueryUnderstanding(confidence=0.0)
    return state


def route_after_understand(state: ChatGraphState) -> str:
    qu = state.get("query_understanding")
    if qu and qu.confidence < settings.chat_confidence_threshold:
        return "clarify"
    return "dispatch_agents"


async def clarify_node(state: ChatGraphState) -> ChatGraphState:
    callback = WsStreamCallback(state["ws_send_fn"], state["conversation_id"])
    text = await clarify_and_stream(state, callback)
    await callback.send_done([])
    state["response"] = text
    state["clarify_mode"] = True
    state["tools_used"] = []
    return state


async def dispatch_agents_node(state: ChatGraphState) -> ChatGraphState:
    qu = state.get("query_understanding")
    plan = qu.dispatch_plan if qu else []
    state["sub_agent_results"] = await execute_dispatch_plan(plan)
    return state


async def synthesize_response_node(state: ChatGraphState) -> ChatGraphState:
    callback = WsStreamCallback(state["ws_send_fn"], state["conversation_id"])
    text, tools = await synthesize_and_stream(state, callback)
    state["response"] = text
    state["tools_used"] = tools
    state["clarify_mode"] = False
    return state


async def update_state_node(state: ChatGraphState) -> ChatGraphState:
    turn_state = state.get("conversation_context") or TurnState()
    qu = state.get("query_understanding")
    response = state.get("response") or ""
    tools_used = state.get("tools_used") or []
    sub_results = state.get("sub_agent_results") or {}

    if qu and qu.entities:
        ent = qu.entities[0]
        turn_state.current_entity = CurrentEntity(
            type=ent.type,
            id=ent.id,
            unit_number=ent.unit_number or (int(ent.identifier) if ent.identifier and ent.identifier.isdigit() else None),
            display_name=ent.resolved_name,
        )
    if qu and qu.time_scope:
        turn_state.current_time_window = TimeWindow(
            start_date=str(qu.time_scope.start_date) if qu.time_scope.start_date else None,
            end_date=str(qu.time_scope.end_date) if qu.time_scope.end_date else None,
            description=qu.time_scope.scope_description,
        )
    if qu:
        turn_state.current_intent = qu.intent
        if qu.intent in {"specific_metric", "explanation", "trend_analysis"}:
            turn_state.current_topic = qu.intent

    abbr = {k: abbreviate_sub_agent_result(k, v.result) for k, v in sub_results.items()}
    turn_entry = TurnHistoryEntry(
        role="assistant",
        content=response,
        entities_referenced=[e.model_dump(mode="json") for e in (qu.entities if qu else [])],
        sub_agents_called=[t.function for t in tools_used] if tools_used else [],
        key_results=abbr,
    )
    user_entry = TurnHistoryEntry(role="user", content=state.get("message", ""))
    turn_state.turn_history = (turn_state.turn_history + [user_entry, turn_entry])[-settings.chat_turn_history_store_limit :]

    await save_turn_state(state["conversation_id"], turn_state)

    conv_id = uuid.UUID(state["conversation_id"])
    async with async_session_factory() as db:
        await append_message(db, conv_id, "user", state.get("message", ""))
        await append_message(
            db,
            conv_id,
            "assistant",
            response,
            [t.model_dump(mode="json") for t in tools_used],
        )
        await db.commit()

    state["turn_state_update"] = TurnStateUpdate(
        current_entity=turn_state.current_entity,
        current_time_window=turn_state.current_time_window,
        current_topic=turn_state.current_topic,
        current_intent=turn_state.current_intent,
        turn_entry=turn_entry,
    )
    return state


def build_graph():
    graph = StateGraph(ChatGraphState)
    graph.add_node("load_context", load_context)
    graph.add_node("understand_query", understand_query_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("dispatch_agents", dispatch_agents_node)
    graph.add_node("synthesize_response", synthesize_response_node)
    graph.add_node("update_state", update_state_node)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "understand_query")
    graph.add_conditional_edges("understand_query", route_after_understand, {"clarify": "clarify", "dispatch_agents": "dispatch_agents"})
    graph.add_edge("clarify", "update_state")
    graph.add_edge("dispatch_agents", "synthesize_response")
    graph.add_edge("synthesize_response", "update_state")
    graph.add_edge("update_state", END)
    return graph.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run_chat_turn(
    message: str,
    conversation_id: str,
    operator_name: str,
    dashboard_context: dict[str, Any] | None,
    ws_send_fn: Callable[[dict[str, Any]], Any],
) -> None:
    lock = _get_lock(conversation_id)
    if lock.locked():
        await ws_send_fn(
            {
                "type": "error",
                "message": "Still working on your last question...",
                "conversation_id": conversation_id,
            }
        )
        return

    async with lock:
        dc = DashboardContext.model_validate(dashboard_context or {})
        state: ChatGraphState = {
            "message": message,
            "conversation_id": conversation_id,
            "operator_name": operator_name,
            "dashboard_context": dc,
            "ws_send_fn": ws_send_fn,
        }
        await get_graph().ainvoke(state)


def mark_summary_scheduled(conversation_id: str) -> bool:
    if conversation_id in _summary_scheduled:
        return False
    _summary_scheduled.add(conversation_id)
    return True
