"""Loop 5 — unknown document rate."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.document import Document


async def compute_unknown_document_rate(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    month_ago = date.today() - timedelta(days=30)
    total = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.created_at >= month_ago,
            )
        )
    ).scalar_one() or 0
    unknown = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.document_type == "unknown",
                Document.created_at >= month_ago,
            )
        )
    ).scalar_one() or 0
    rate = unknown / total * 100 if total else 0.0
    period_start = date.today().replace(day=1)
    await upsert_fleet_metric(
        db,
        entity_type="fleet",
        entity_id=None,
        metric_name="unknown_document_rate",
        value=Decimal(str(round(rate, 4))),
        period_type="monthly",
        period_start=period_start,
        period_end=period_start + timedelta(days=31),
        tenant_id=tenant_id,
    )
    return {"unknown_document_rate_pct": round(rate, 2), "unknown_count": unknown}
