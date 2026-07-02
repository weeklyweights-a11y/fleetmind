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
