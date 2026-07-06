"""Vendor price increase detection."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.maintenance_event import MaintenanceEvent
from app.models.vendor import Vendor


async def detect_vendor_cost_increase(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    today = date.today()
    quarter_start = today - timedelta(days=90)
    six_months = today - timedelta(days=180)

    recent = (
        await db.execute(
            select(MaintenanceEvent).where(
                MaintenanceEvent.vendor_id == vendor_id,
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= quarter_start,
            )
        )
    ).scalars().all()
    historical = (
        await db.execute(
            select(MaintenanceEvent).where(
                MaintenanceEvent.vendor_id == vendor_id,
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= six_months,
                MaintenanceEvent.service_date < quarter_start,
            )
        )
    ).scalars().all()
    if not recent or not historical:
        return []

    recent_avg = float(sum(e.total_cost for e in recent) / len(recent))
    hist_avg = float(sum(e.total_cost for e in historical) / len(historical))
    if hist_avg == 0:
        return []
    pct = recent_avg / hist_avg * 100
    if pct < THRESHOLDS.vendor_cost_increase_pct:
        return []

    vname = (await db.execute(select(Vendor.name).where(Vendor.id == vendor_id))).scalar_one_or_none()
    increase = pct - 100
    return [
        AnomalyCandidate(
            anomaly_type="vendor_cost_increase",
            entity_type="vendor",
            entity_id=vendor_id,
            description=(
                f"{vname}'s average invoice went from ${hist_avg:,.0f} to ${recent_avg:,.0f} "
                f"— {increase:.0f}% increase in the last quarter."
            ),
            severity="warning",
            supporting_data={
                "metric": "vendor_avg_invoice",
                "current_value": recent_avg,
                "baseline_mean": hist_avg,
                "increase_pct": round(increase, 1),
            },
            dedup_key=f"vendor_cost_increase:vendor:{vendor_id}:vendor_avg_invoice",
        )
    ]
