"""Per-driver baseline metrics."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.assignment import Assignment
from app.models.driver import Driver


async def compute_driver_baselines(
    db: AsyncSession,
    driver_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> int:
    today = date.today()
    period_start = today.replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    assignments = (
        await db.execute(
            select(Assignment).where(Assignment.driver_id == driver_id, Assignment.tenant_id == tenant_id)
        )
    ).scalars().all()
    if not assignments:
        return 0

    durations = []
    trucks = set()
    for a in assignments:
        trucks.add(a.truck_id)
        end = a.end_date or today
        durations.append((end - a.start_date).days)

    avg_days = sum(durations) / len(durations)
    written = 0
    await upsert_fleet_metric(
        db,
        entity_type="driver",
        entity_id=driver_id,
        metric_name="driver_assignment_stability_days",
        value=Decimal(str(round(avg_days, 4))),
        period_type="all_time",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    written += 1
    await upsert_fleet_metric(
        db,
        entity_type="driver",
        entity_id=driver_id,
        metric_name="driver_trucks_operated_count",
        value=Decimal(str(len(trucks))),
        period_type="all_time",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    written += 1
    return written


async def compute_all_driver_baselines(db: AsyncSession, *, tenant_id: int = 1) -> int:
    drivers = (await db.execute(select(Driver.id).where(Driver.tenant_id == tenant_id))).scalars().all()
    total = 0
    for did in drivers:
        total += await compute_driver_baselines(db, did, tenant_id=tenant_id)
    return total
