"""Unresolved conversation items checker."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.anomalies.service import upsert_anomaly
from app.intelligence.config import THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.conversation import Conversation
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck


async def run_unresolved_checker(
    db: AsyncSession,
    *,
    tenant_id: int = 1,
    truck_id: uuid.UUID | None = None,
) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=THRESHOLDS.unresolved_item_max_age_days)
    stmt = select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.unresolved_items.isnot(None),
        Conversation.ended_at.isnot(None),
        Conversation.ended_at > cutoff,
    )
    created = 0
    for conv in (await db.execute(stmt)).scalars().all():
        items = conv.unresolved_items
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("entity_id")
            category = item.get("description", "")
            if not entity_id:
                continue
            try:
                tid = uuid.UUID(str(entity_id))
            except ValueError:
                continue
            if truck_id and tid != truck_id:
                continue
            new_events = (
                await db.execute(
                    select(MaintenanceEvent).where(
                        MaintenanceEvent.truck_id == tid,
                        MaintenanceEvent.tenant_id == tenant_id,
                        MaintenanceEvent.service_date > conv.ended_at.date(),
                    )
                )
            ).scalars().all()
            if category:
                cat_lower = category.lower()
                new_events = [e for e in new_events if cat_lower in e.category.lower() or cat_lower in e.description.lower()]
            if not new_events:
                continue
            unit = (await db.execute(select(Truck.unit_number).where(Truck.id == tid))).scalar_one_or_none()
            e = new_events[0]
            candidate = AnomalyCandidate(
                anomaly_type="recurring_issue",
                entity_type="truck",
                entity_id=tid,
                description=(
                    f"Follow-up: you asked to monitor truck {unit} on {conv.ended_at.date()}. "
                    f"New {e.category} repair on {e.service_date} for ${float(e.total_cost):,.0f}."
                ),
                severity="warning",
                supporting_data={
                    "follow_up": True,
                    "conversation_id": str(conv.id),
                    "unresolved_item": item,
                    "metric": "follow_up",
                },
            )
            _, was_created = await upsert_anomaly(db, candidate, tenant_id=tenant_id)
            if was_created:
                created += 1
    return {"anomalies_created": created}
