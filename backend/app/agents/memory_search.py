"""Memory search sub-agent (Phase 5 data stub)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.schemas.conversations import MatchingConversation, MemorySearchResponse


async def get_memory_search(
    db: AsyncSession,
    query: str,
    operator_name: str | None = None,
    tenant_id: int = 1,
) -> MemorySearchResponse:
    if not query.strip():
        return MemorySearchResponse(matching_conversations=[])

    q = query.strip().lower()
    stmt = select(Conversation).where(Conversation.tenant_id == tenant_id)
    if operator_name:
        stmt = stmt.where(Conversation.operator_name.ilike(f"%{operator_name}%"))

    stmt = stmt.where(
        or_(
            Conversation.summary_text.ilike(f"%{q}%"),
        )
    ).limit(20)

    rows = (await db.execute(stmt)).scalars().all()
    matches: list[MatchingConversation] = []
    for row in rows:
        matches.append(
            MatchingConversation(
                conversation_id=row.id,
                date=row.started_at,
                summary=row.summary_text,
                entities_discussed=row.entities_discussed,
                topics=row.topics,
                key_findings=row.key_findings,
                unresolved_items=row.unresolved_items,
                relevance_score=1.0,
            )
        )

    return MemorySearchResponse(matching_conversations=matches)
