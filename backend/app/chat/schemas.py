"""Pydantic schemas and LangGraph state for the chat agent."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

from app.chat import intents


class EntityRef(BaseModel):
    type: str
    identifier: str | None = None
    resolved_name: str | None = None
    id: UUID | None = None
    unit_number: int | None = None


class TimeScope(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    scope_description: str | None = None


class DispatchPlanItem(BaseModel):
    function: str
    params: dict[str, Any] = Field(default_factory=dict)


class QueryUnderstanding(BaseModel):
    entities: list[EntityRef] = Field(default_factory=list)
    time_scope: TimeScope | None = None
    intent: str = intents.ENTITY_OVERVIEW
    dispatch_plan: list[DispatchPlanItem] = Field(default_factory=list)
    response_guidance: str = ""
    confidence: float = 1.0


class CurrentEntity(BaseModel):
    type: str
    id: UUID | None = None
    unit_number: int | None = None
    display_name: str | None = None


class TimeWindow(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class TurnHistoryEntry(BaseModel):
    role: str
    content: str
    entities_referenced: list[dict[str, Any]] = Field(default_factory=list)
    sub_agents_called: list[str] = Field(default_factory=list)
    key_results: dict[str, Any] = Field(default_factory=dict)


class TurnState(BaseModel):
    current_entity: CurrentEntity | None = None
    current_time_window: TimeWindow | None = None
    current_topic: str | None = None
    current_intent: str | None = None
    turn_history: list[TurnHistoryEntry] = Field(default_factory=list)
    last_activity_at: str | None = None
    recent_summaries: list[dict[str, Any]] = Field(default_factory=list)
    proactive_alerts: list[dict[str, Any]] = Field(default_factory=list)


class DashboardContext(BaseModel):
    current_page: str | None = None
    current_entity: dict[str, Any] | None = None
    visible_panels: list[str] = Field(default_factory=list)


class SubAgentResult(BaseModel):
    function: str
    status: str = "ok"
    result: dict[str, Any] | None = None
    error: str | None = None
    empty: bool = False


class ToolsUsedEntry(BaseModel):
    function: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    result_summary: str = ""


class TurnStateUpdate(BaseModel):
    current_entity: CurrentEntity | None = None
    current_time_window: TimeWindow | None = None
    current_topic: str | None = None
    current_intent: str | None = None
    turn_entry: TurnHistoryEntry | None = None


class OperatorProfileSnapshot(BaseModel):
    operator_name: str
    frequent_entities: list[dict[str, Any]] = Field(default_factory=list)
    frequent_topics: list[dict[str, Any]] = Field(default_factory=list)
    preferred_response_style: str | None = None
    query_preferences: dict[str, Any] = Field(default_factory=dict)
    total_conversations: int = 0


class ChatGraphState(TypedDict, total=False):
    message: str
    conversation_id: str
    operator_name: str
    conversation_context: TurnState
    operator_profile: OperatorProfileSnapshot
    recent_summaries: list[dict[str, Any]]
    dashboard_context: DashboardContext
    proactive_alerts: list[dict[str, Any]]
    query_understanding: QueryUnderstanding
    sub_agent_results: dict[str, SubAgentResult]
    response: str
    turn_state_update: TurnStateUpdate
    tools_used: list[ToolsUsedEntry]
    clarify_mode: bool
    ws_send_fn: Callable[..., Any]


class ConversationMessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    tools_called: Any = None
    message_index: int
    created_at: datetime | None = None


class ConversationDetail(BaseModel):
    id: UUID
    operator_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    entities_discussed: Any = None
    topics: Any = None
    key_findings: Any = None
    unresolved_items: Any = None
    summary_text: str | None = None


class ChatStartedResponse(BaseModel):
    type: str = "chat_started"
    conversation_id: UUID
    resumed: bool = False
