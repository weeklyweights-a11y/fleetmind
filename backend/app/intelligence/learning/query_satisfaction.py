"""Loop 3 — query satisfaction."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.conversation import Conversation
from datetime import date, timedelta
from decimal import Decimal


async def compute_query_satisfaction(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    convs = (
        await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.ended_at.isnot(None),
            )
        )
    ).scalars().all()
    total = len(convs)
    satisfied = 0
    for c in convs:
        topics = c.topics if isinstance(c.topics, list) else []
        if any(isinstance(t, dict) and t.get("intent") != "clarification" for t in topics):
            satisfied += 1
    rate = satisfied / total * 100 if total else 0.0
    today = date.today()
    period_start = today.replace(day=1)
    period_end = period_start + timedelta(days=31)
    await upsert_fleet_metric(
        db,
        entity_type="fleet",
        entity_id=None,
        metric_name="query_satisfaction_rate",
        value=Decimal(str(round(rate, 4))),
        period_type="monthly",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    return {"query_satisfaction_rate_pct": round(rate, 2), "total_conversations": total}
