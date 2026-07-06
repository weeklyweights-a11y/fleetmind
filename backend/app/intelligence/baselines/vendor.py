"""Per-vendor baseline metrics."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.maintenance_event import MaintenanceEvent
from app.models.vendor import Vendor


async def compute_vendor_baselines(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> int:
    today = date.today()
    period_start = today.replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    count = (
        await db.execute(
            select(func.count())
            .select_from(MaintenanceEvent)
            .where(MaintenanceEvent.vendor_id == vendor_id, MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalar_one() or 0
    if count < THRESHOLDS.vendor_min_events:
        return 0

    events = (
        await db.execute(
            select(MaintenanceEvent)
            .where(MaintenanceEvent.vendor_id == vendor_id, MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalars().all()

    written = 0
    avg_invoice = float(sum(e.total_cost for e in events) / len(events))
    await upsert_fleet_metric(
        db,
        entity_type="vendor",
        entity_id=vendor_id,
        metric_name="vendor_avg_invoice",
        value=Decimal(str(round(avg_invoice, 4))),
        period_type="all_time",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    written += 1

    truck_visits: dict[uuid.UUID, int] = {}
    for e in events:
        truck_visits[e.truck_id] = truck_visits.get(e.truck_id, 0) + 1

    await upsert_fleet_metric(
        db,
        entity_type="vendor",
        entity_id=vendor_id,
        metric_name="vendor_truck_coverage_count",
        value=Decimal(str(len(truck_visits))),
        period_type="all_time",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    written += 1

    for truck_id, visits in truck_visits.items():
        await upsert_fleet_metric(
            db,
            entity_type="vendor",
            entity_id=vendor_id,
            metric_name=f"vendor_truck_{truck_id}_visit_frequency",
            value=Decimal(str(visits)),
            period_type="all_time",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 1

    return written


async def compute_all_vendor_baselines(db: AsyncSession, *, tenant_id: int = 1) -> int:
    vendors = (await db.execute(select(Vendor.id).where(Vendor.tenant_id == tenant_id))).scalars().all()
    total = 0
    for vid in vendors:
        total += await compute_vendor_baselines(db, vid, tenant_id=tenant_id)
    return total
