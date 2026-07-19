"""Recurring maintenance category detection."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck


async def detect_recurring_issue(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    cutoff = date.today() - timedelta(days=THRESHOLDS.recurring_issue_months * 30)
    events = (
        await db.execute(
            select(MaintenanceEvent).where(
                MaintenanceEvent.truck_id == truck_id,
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= cutoff,
            )
        )
    ).scalars().all()

    by_cat: dict[str, list] = {}
    for e in events:
        by_cat.setdefault(e.category, []).append(e)

    candidates: list[AnomalyCandidate] = []
    unit = (await db.execute(select(Truck.unit_number).where(Truck.id == truck_id))).scalar_one_or_none()
    for cat, cat_events in by_cat.items():
        if len(cat_events) < THRESHOLDS.recurring_issue_count:
            continue
        total = sum(float(e.total_cost) for e in cat_events)
        candidates.append(
            AnomalyCandidate(
                anomaly_type="recurring_issue",
                entity_type="truck",
                entity_id=truck_id,
                description=(
                    f"Truck {unit} has had {len(cat_events)} {cat} repairs in "
                    f"{THRESHOLDS.recurring_issue_months} months totaling ${total:,.0f}."
                ),
                severity="warning",
                supporting_data={
                    "metric": "category_event_count",
                    "category": cat,
                    "current_value": len(cat_events),
                    "total_cost": total,
                },
                dedup_key=f"recurring_issue:truck:{truck_id}:{cat}",
            )
        )
    return candidates
