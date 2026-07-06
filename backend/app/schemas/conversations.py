from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MatchingConversation(BaseModel):
    conversation_id: UUID
    date: datetime
    summary: str | None = None
    entities_discussed: Any = None
    topics: Any = None
    key_findings: Any = None
    unresolved_items: Any = None
    relevance_score: float = 1.0


class MemorySearchResponse(BaseModel):
    matching_conversations: list[MatchingConversation] = Field(default_factory=list)


class ConversationMessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    tools_called: Any = None
    message_index: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class UnresolvedItemsResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
