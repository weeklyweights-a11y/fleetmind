"""Unusual service frequency detection."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.metrics_store import get_fleet_metric
from app.intelligence.schemas import AnomalyCandidate
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck


async def detect_frequency_unusual(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    month_start = date.today().replace(day=1)
    count = (
        await db.execute(
            select(func.count()).select_from(MaintenanceEvent).where(
                MaintenanceEvent.truck_id == truck_id,
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= month_start,
            )
        )
    ).scalar_one() or 0

    mean_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="maintenance_monthly_event_count_mean", period_type="monthly", tenant_id=tenant_id,
    )
    sd_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="maintenance_monthly_event_count_sd", period_type="monthly", tenant_id=tenant_id,
    )
    if not mean_row:
        return []
    mean = float(mean_row.metric_value)
    sd = float(sd_row.metric_value) if sd_row else 0.0
    if sd == 0:
        threshold = mean + 1
    else:
        threshold = mean + THRESHOLDS.cost_spike_sd_warning * sd
    if count <= threshold:
        return []

    unit = (await db.execute(select(Truck.unit_number).where(Truck.id == truck_id))).scalar_one_or_none()
    return [
        AnomalyCandidate(
            anomaly_type="frequency_unusual",
            entity_type="truck",
            entity_id=truck_id,
            description=(
                f"Truck {unit} had {count} service visits this month vs average of {mean:.1f}/month."
            ),
            severity="warning",
            supporting_data={
                "metric": "monthly_event_count",
                "current_value": count,
                "baseline_mean": mean,
                "baseline_sd": sd,
                "period": date.today().strftime("%Y-%m"),
            },
        )
    ]
