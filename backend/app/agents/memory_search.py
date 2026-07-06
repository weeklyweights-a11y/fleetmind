"""Memory search sub-agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationMessage
from app.schemas.conversations import MatchingConversation, MemorySearchResponse


async def get_memory_search(
    db: AsyncSession,
    query: str,
    operator_name: str | None = None,
    since_days: int | None = None,
    tenant_id: int = 1,
) -> MemorySearchResponse:
    if not query.strip():
        return MemorySearchResponse(matching_conversations=[])

    q = query.strip().lower()
    stmt = select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.ended_at.isnot(None),
    )
    if operator_name:
        stmt = stmt.where(Conversation.operator_name.ilike(f"%{operator_name}%"))
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = stmt.where(Conversation.ended_at >= cutoff)

    stmt = stmt.where(
        or_(
            Conversation.summary_text.ilike(f"%{q}%"),
            cast(Conversation.entities_discussed, String).ilike(f"%{q}%"),
            cast(Conversation.topics, String).ilike(f"%{q}%"),
            cast(Conversation.key_findings, String).ilike(f"%{q}%"),
        )
    ).limit(20)

    rows = (await db.execute(stmt)).scalars().all()
    matches: list[MatchingConversation] = []
    seen: set = set()

    for row in rows:
        score = 1.0
        if row.summary_text and q in row.summary_text.lower():
            score += 0.5
        matches.append(
            MatchingConversation(
                conversation_id=row.id,
                date=row.ended_at or row.started_at,
                summary=row.summary_text,
                entities_discussed=row.entities_discussed,
                topics=row.topics,
                key_findings=row.key_findings,
                unresolved_items=row.unresolved_items,
                relevance_score=score,
            )
        )
        seen.add(row.id)

    msg_stmt = (
        select(ConversationMessage, Conversation)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.ended_at.isnot(None),
            ConversationMessage.content.ilike(f"%{q}%"),
        )
    )
    if operator_name:
        msg_stmt = msg_stmt.where(Conversation.operator_name.ilike(f"%{operator_name}%"))
    msg_stmt = msg_stmt.limit(20)
    for msg, conv in (await db.execute(msg_stmt)).all():
        if conv.id in seen:
            continue
        matches.append(
            MatchingConversation(
                conversation_id=conv.id,
                date=conv.ended_at or conv.started_at,
                summary=conv.summary_text,
                entities_discussed=conv.entities_discussed,
                topics=conv.topics,
                key_findings=conv.key_findings,
                unresolved_items=conv.unresolved_items,
                relevance_score=0.8,
            )
        )

    matches.sort(key=lambda m: m.relevance_score, reverse=True)
    return MemorySearchResponse(matching_conversations=matches[:20])
