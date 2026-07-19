"""Operator profile updates after conversations."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.prompts import load_prompt
from app.chat.session import load_operator_profile
from app.models.conversation import Conversation, ConversationMessage
from app.services.gemini_client import generate_json


def _merge_ranked_counts(
    existing: list[dict[str, Any]] | None,
    new_items: list[dict[str, Any]],
    key_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    meta: dict[str, dict[str, Any]] = {}
    for item in existing or []:
        if not isinstance(item, dict):
            continue
        key = "|".join(str(item.get(f, "")) for f in key_fields)
        counts[key] += int(item.get("count", 1))
        meta[key] = item
    for item in new_items:
        key = "|".join(str(item.get(f, "")) for f in key_fields)
        counts[key] += 1
        meta[key] = {**item, "count": counts[key]}
    ranked = sorted(meta.values(), key=lambda x: int(x.get("count", 0)), reverse=True)
    for item in ranked:
        key = "|".join(str(item.get(f, "")) for f in key_fields)
        item["count"] = counts[key]
    return ranked[:50]


async def update_profile_after_conversation(
    db: AsyncSession,
    operator_name: str,
    summary: dict[str, Any],
    tenant_id: int = 1,
) -> None:
    profile = await load_operator_profile(db, operator_name, tenant_id)
    entities = summary.get("entities_discussed") or []
    topics = summary.get("topics") or []
    entity_items = [e for e in entities if isinstance(e, dict)]
    topic_items = [{"topic": t, "count": 1} if isinstance(t, str) else t for t in topics if t]
    profile.frequent_entities = _merge_ranked_counts(
        profile.frequent_entities if isinstance(profile.frequent_entities, list) else [],
        entity_items,
        ("type", "id", "name"),
    )
    profile.frequent_topics = _merge_ranked_counts(
        profile.frequent_topics if isinstance(profile.frequent_topics, list) else [],
        topic_items,
        ("topic",),
    )
    prefs = summary.get("query_preferences") or summary.get("operator_preferences")
    if isinstance(prefs, dict):
        existing = profile.query_preferences if isinstance(profile.query_preferences, dict) else {}
        merged = {**existing, **prefs}
        profile.query_preferences = merged
    profile.total_conversations = int(profile.total_conversations or 0) + 1
    profile.last_active = datetime.now(timezone.utc)
    await db.flush()


async def maybe_infer_response_style(db: AsyncSession, operator_name: str, tenant_id: int = 1) -> None:
    profile = await load_operator_profile(db, operator_name, tenant_id)
    if int(profile.total_conversations or 0) % 10 != 0:
        return
    convs = (
        await db.execute(
            select(Conversation)
            .where(Conversation.operator_name == operator_name, Conversation.tenant_id == tenant_id)
            .order_by(Conversation.started_at.desc())
            .limit(10)
        )
    ).scalars().all()
    if not convs:
        return
    lines: list[str] = []
    for conv in convs:
        msgs = (
            await db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conv.id)
                .order_by(ConversationMessage.message_index)
            )
        ).scalars().all()
        for m in msgs:
            lines.append(f"{m.role}: {m.content[:500]}")
    prompt = load_prompt("operator_style_inference.txt").replace("{{operator_name}}", operator_name)
    prompt += "\n\nTranscripts:\n" + "\n".join(lines[-80:])
    try:
        result = await generate_json(prompt)
        style = result.get("preferred_response_style")
        if style:
            profile.preferred_response_style = str(style)
            await db.flush()
    except Exception:
        pass
