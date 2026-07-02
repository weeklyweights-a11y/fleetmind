"""Fleet-wide maintenance aggregates for financial dashboard."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maintenance_event import MaintenanceEvent
from app.schemas.fleet import (
    FleetCategorySpend,
    FleetMaintenanceMonthPoint,
    FleetMaintenanceSummaryResponse,
)


async def get_fleet_maintenance_summary(
    db: AsyncSession,
    tenant_id: int = 1,
) -> FleetMaintenanceSummaryResponse:
    events = (
        await db.execute(
            select(MaintenanceEvent).where(MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalars().all()

    monthly: dict[str, list] = {}
    by_cat: dict[str, list] = {}
    for e in events:
        month = e.service_date.strftime("%Y-%m")
        monthly.setdefault(month, []).append(e)
        by_cat.setdefault(e.category, []).append(e)

    monthly_trend = [
        FleetMaintenanceMonthPoint(
            month=m,
            spend=sum(x.total_cost for x in evts),
            event_count=len(evts),
        )
        for m, evts in sorted(monthly.items())
    ]
    by_category = sorted(
        [
            FleetCategorySpend(
                category=cat,
                spend=sum(x.total_cost for x in evts),
                count=len(evts),
            )
            for cat, evts in by_cat.items()
        ],
        key=lambda x: x.spend,
        reverse=True,
    )
    return FleetMaintenanceSummaryResponse(monthly_trend=monthly_trend, by_category=by_category)
