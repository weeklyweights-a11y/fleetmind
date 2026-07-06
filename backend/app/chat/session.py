"""Redis turn state and Postgres conversation persistence.

Redis key prefix chat_sessions:{id} maps to spec session:{conversation_id}.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.conversation import Conversation, ConversationMessage
from app.models.operator_profile import OperatorProfile
from app.redis_client import get_chat_session, set_chat_session
from app.chat.schemas import TurnState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def turn_state_from_session(data: dict[str, Any] | None) -> TurnState:
    if not data:
        return TurnState()
    turn = data.get("turn_state")
    if turn:
        return TurnState.model_validate(turn)
    return TurnState()


def session_to_dict(turn_state: TurnState, **extra: Any) -> dict[str, Any]:
    payload = {"turn_state": turn_state.model_dump(mode="json"), **extra}
    return payload


async def save_turn_state(conversation_id: str, turn_state: TurnState, **extra: Any) -> None:
    turn_state.last_activity_at = _utcnow().isoformat()
    await set_chat_session(
        conversation_id,
        session_to_dict(turn_state, **extra),
        ttl_seconds=settings.chat_session_ttl_seconds,
    )


async def load_turn_state(conversation_id: str) -> TurnState:
    data = await get_chat_session(conversation_id)
    return turn_state_from_session(data)


async def touch_session_activity(conversation_id: str) -> None:
    data = await get_chat_session(conversation_id)
    if not data:
        return
    turn_state = turn_state_from_session(data)
    await save_turn_state(conversation_id, turn_state, **{k: v for k, v in data.items() if k != "turn_state"})


async def create_conversation(db: AsyncSession, operator_name: str, tenant_id: int = 1) -> uuid.UUID:
    row = Conversation(operator_name=operator_name, tenant_id=tenant_id)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row.id


async def resume_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> bool:
    session = await get_chat_session(str(conversation_id))
    if not session:
        return False
    row = await db.get(Conversation, conversation_id)
    return row is not None and row.ended_at is None


async def load_operator_profile(db: AsyncSession, operator_name: str, tenant_id: int = 1) -> OperatorProfile:
    result = await db.execute(
        select(OperatorProfile).where(
            OperatorProfile.tenant_id == tenant_id,
            OperatorProfile.operator_name == operator_name,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = OperatorProfile(operator_name=operator_name, tenant_id=tenant_id)
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
    return profile


async def load_recent_summaries(
    db: AsyncSession,
    operator_name: str,
    limit: int = 5,
    tenant_id: int = 1,
) -> list[dict[str, Any]]:
    stmt = (
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.operator_name == operator_name,
            Conversation.ended_at.isnot(None),
        )
        .order_by(Conversation.ended_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "conversation_id": str(r.id),
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "summary_text": r.summary_text,
            "topics": r.topics,
            "key_findings": r.key_findings,
            "entities_discussed": r.entities_discussed,
            "unresolved_items": r.unresolved_items,
        }
        for r in rows
    ]


async def append_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    tools_called: list[dict[str, Any]] | None = None,
) -> ConversationMessage:
    idx_result = await db.execute(
        select(func.coalesce(func.max(ConversationMessage.message_index), -1)).where(
            ConversationMessage.conversation_id == conversation_id
        )
    )
    next_index = int(idx_result.scalar_one()) + 1
    msg = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tools_called=tools_called,
        message_index=next_index,
        tenant_id=1,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def get_messages(db: AsyncSession, conversation_id: uuid.UUID) -> list[ConversationMessage]:
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.message_index)
    )
    return list(result.scalars().all())


async def get_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    return await db.get(Conversation, conversation_id)


async def end_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    row = await db.get(Conversation, conversation_id)
    if row is None:
        return None
    if row.ended_at is not None:
        return row
    row.ended_at = _utcnow()
    await db.flush()
    return row


async def get_active_unresolved_items(
    db: AsyncSession,
    operator_name: str,
    limit: int = 20,
    tenant_id: int = 1,
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = (
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.operator_name == operator_name,
            Conversation.unresolved_items.isnot(None),
            Conversation.ended_at.isnot(None),
            Conversation.ended_at > cutoff,
        )
        .order_by(Conversation.ended_at.desc().nullslast())
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for conv in (await db.execute(stmt)).scalars().all():
        raw = conv.unresolved_items
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    items.append({**item, "conversation_id": str(conv.id)})
    return items


async def append_investigating_unresolved_item(
    db: AsyncSession,
    operator_name: str,
    *,
    anomaly_id: uuid.UUID,
    description: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    tenant_id: int = 1,
) -> None:
    """Append an investigating anomaly to the operator's latest conversation unresolved list."""
    conv = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.operator_name == operator_name,
            )
            .order_by(Conversation.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if conv is None:
        return
    existing = conv.unresolved_items if isinstance(conv.unresolved_items, list) else []
    aid = str(anomaly_id)
    if any(isinstance(i, dict) and i.get("anomaly_id") == aid for i in existing):
        return
    item = {
        "description": f"Investigating: {description}",
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "anomaly_id": aid,
        "source": "investigate",
    }
    conv.unresolved_items = [*existing, item]
    await db.flush()


async def init_chat_session(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    operator_name: str,
) -> TurnState:
    profile = await load_operator_profile(db, operator_name)
    summaries = await load_recent_summaries(db, operator_name)
    from app.chat.proactive_context import load_proactive_alerts

    alerts = await load_proactive_alerts(db)
    turn_state = TurnState(recent_summaries=summaries, proactive_alerts=alerts)
    await save_turn_state(
        str(conversation_id),
        turn_state,
        operator_name=operator_name,
        profile_snapshot={
            "operator_name": profile.operator_name,
            "frequent_entities": profile.frequent_entities or [],
            "frequent_topics": profile.frequent_topics or [],
            "preferred_response_style": profile.preferred_response_style,
            "query_preferences": profile.query_preferences if isinstance(profile.query_preferences, dict) else {},
            "total_conversations": profile.total_conversations,
        },
    )
    return turn_state
