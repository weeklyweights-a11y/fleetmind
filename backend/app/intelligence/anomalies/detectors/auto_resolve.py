"""Auto-resolve cost spikes when spend normalizes."""

from __future__ import annotations


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.anomalies.service import resolve_cost_spikes_for_truck
from app.models.truck import Truck


async def run_auto_resolvers(db: AsyncSession, *, tenant_id: int = 1) -> int:
    resolved = 0
    trucks = (await db.execute(select(Truck.id).where(Truck.tenant_id == tenant_id))).scalars().all()
    for tid in trucks:
        resolved += await resolve_cost_spikes_for_truck(db, tid, tenant_id=tenant_id)
    return resolved
