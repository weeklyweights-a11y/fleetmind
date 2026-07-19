"""Orchestrate baseline recomputation."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.baselines.driver import compute_all_driver_baselines
from app.intelligence.baselines.fleet import compute_fleet_baselines
from app.intelligence.baselines.truck import compute_truck_baselines
from app.intelligence.baselines.vendor import compute_all_vendor_baselines, compute_vendor_baselines
from app.models.truck import Truck


async def recompute_truck(db: AsyncSession, truck_id: uuid.UUID, *, tenant_id: int = 1) -> int:
    return await compute_truck_baselines(db, truck_id, tenant_id=tenant_id)


async def recompute_vendor(db: AsyncSession, vendor_id: uuid.UUID, *, tenant_id: int = 1) -> int:
    return await compute_vendor_baselines(db, vendor_id, tenant_id=tenant_id)


async def recompute_fleet(db: AsyncSession, *, tenant_id: int = 1) -> int:
    return await compute_fleet_baselines(db, tenant_id=tenant_id)


async def recompute_all(db: AsyncSession, *, tenant_id: int = 1) -> int:
    total = 0
    trucks = (
        await db.execute(select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.status == "active"))
    ).scalars().all()
    for tid in trucks:
        total += await compute_truck_baselines(db, tid, tenant_id=tenant_id)
    total += await compute_fleet_baselines(db, tenant_id=tenant_id)
    total += await compute_all_vendor_baselines(db, tenant_id=tenant_id)
    total += await compute_all_driver_baselines(db, tenant_id=tenant_id)
    return total
