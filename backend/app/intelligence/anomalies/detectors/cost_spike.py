"""Cost spike detection."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.metrics_store import get_fleet_metric
from app.intelligence.schemas import AnomalyCandidate
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck


async def detect_cost_spike(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    mean_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="maintenance_monthly_spend_mean", period_type="monthly", tenant_id=tenant_id,
    )
    sd_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="maintenance_monthly_spend_sd", period_type="monthly", tenant_id=tenant_id,
    )
    latest_row = await get_fleet_metric(
        db, entity_type="truck", entity_id=truck_id,
        metric_name="maintenance_monthly_spend_latest", period_type="monthly", tenant_id=tenant_id,
    )
    if not mean_row or not latest_row:
        return []

    mean = float(mean_row.metric_value)
    sd = float(sd_row.metric_value) if sd_row else 0.0
    latest = float(latest_row.metric_value)
    if sd == 0 and mean == 0:
        return []
    deviation_sd = (latest - mean) / sd if sd > 0 else (latest / mean if mean else 0)
    if deviation_sd < THRESHOLDS.cost_spike_sd_warning:
        return []

    unit = (await db.execute(select(Truck.unit_number).where(Truck.id == truck_id))).scalar_one_or_none()
    severity = "critical" if deviation_sd >= THRESHOLDS.cost_spike_sd_critical else "warning"
    supporting = {
        "metric": "maintenance_monthly_spend",
        "current_value": latest,
        "baseline_mean": mean,
        "baseline_sd": sd,
        "deviation_sd": round(deviation_sd, 2),
        "period": date.today().strftime("%Y-%m"),
    }

    # Planned overhaul heuristic
    month_start = date.today().replace(day=1)
    recent = (
        await db.execute(
            select(MaintenanceEvent).where(
                MaintenanceEvent.truck_id == truck_id,
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= month_start,
            )
        )
    ).scalars().all()
    for e in recent:
        if float(e.total_cost) > THRESHOLDS.planned_overhaul_cost and e.category in (
            "Engine", "Transmission",
        ):
            severity = "info"
            supporting["possible_planned_overhaul"] = True
            break

    ratio = latest / mean if mean else 0
    return [
        AnomalyCandidate(
            anomaly_type="cost_spike",
            entity_type="truck",
            entity_id=truck_id,
            description=(
                f"Truck {unit} spent ${latest:,.0f} on maintenance this month "
                f"vs monthly average of ${mean:,.0f} ({ratio:.1f}x above average)."
            ),
            severity=severity,
            supporting_data=supporting,
            dedup_key=f"cost_spike:truck:{truck_id}:maintenance_monthly_spend",
        )
    ]
