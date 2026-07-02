"""Resolve truck UUID to unit number for NOTIFY payloads."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.truck import Truck


async def resolve_truck_unit(db: AsyncSession, truck_id: str | uuid.UUID | None) -> int | None:
    if not truck_id:
        return None
    try:
        tid = truck_id if isinstance(truck_id, uuid.UUID) else uuid.UUID(str(truck_id))
    except ValueError:
        return None
    result = await db.execute(select(Truck.unit_number).where(Truck.id == tid))
    return result.scalar_one_or_none()
