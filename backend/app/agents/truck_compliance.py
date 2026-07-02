"""Truck compliance sub-agent."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import (
    build_truck_compliance_categories,
    build_urgent_items,
    overall_status_from_categories,
)
from app.schemas.trucks import TruckComplianceResponse


async def get_truck_compliance(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckComplianceResponse:
    categories = await build_truck_compliance_categories(db, truck_id, tenant_id)
    statuses = [
        categories.insurance.status,
        categories.registration.status,
        categories.title.status,
        categories.emission.status,
        categories.driver_cdl.status,
        categories.medical_cert.status,
    ]
    overall = overall_status_from_categories(statuses)
    urgent = build_urgent_items(categories)

    return TruckComplianceResponse(
        overall_status=overall,  # type: ignore[arg-type]
        categories=categories,
        urgent_items=urgent,
    )
