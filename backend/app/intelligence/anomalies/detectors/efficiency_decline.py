"""Cost per mile decline detection."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.metrics_store import get_fleet_metric
from app.intelligence.schemas import AnomalyCandidate
from app.models.truck import Truck
from sqlalchemy import select


async def detect_efficiency_decline(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    cpm_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="cost_per_mile", period_type="all_time", tenant_id=tenant_id,
    )
    if not cpm_row:
        return []
    current = float(cpm_row.metric_value)
    # Use fleet avg as rolling baseline proxy when historical CPM rows unavailable
    fleet_row = await get_fleet_metric(
        db, entity_type="fleet", entity_id=None,
        metric_name="fleet_avg_cost_per_event", period_type="all_time", tenant_id=tenant_id,
    )
    if not fleet_row:
        return []
    baseline = float(fleet_row.metric_value) / 100  # rough miles proxy
    if baseline == 0:
        return []
    increase_pct = (current - baseline) / baseline * 100
    if increase_pct < THRESHOLDS.efficiency_decline_pct:
        return []

    unit = (await db.execute(select(Truck.unit_number).where(Truck.id == truck_id))).scalar_one_or_none()
    return [
        AnomalyCandidate(
            anomaly_type="efficiency_decline",
            entity_type="truck",
            entity_id=truck_id,
            description=f"Truck {unit} cost per mile ${current:.2f} is {increase_pct:.0f}% above baseline.",
            severity="warning",
            supporting_data={
                "metric": "cost_per_mile",
                "current_value": current,
                "baseline_mean": baseline,
                "increase_pct": round(increase_pct, 1),
            },
        )
    ]
