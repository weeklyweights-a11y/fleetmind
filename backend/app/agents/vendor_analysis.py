"""Vendor analysis sub-agent."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.schemas.vendors import (
    VendorByCategory,
    VendorByTruck,
    VendorConcentration,
    VendorCostComparison,
    VendorDetailInfo,
    VendorDetailResponse,
    VendorFleetItem,
    VendorFleetResponse,
    VendorSummary,
    VendorTrendPoint,
)


async def get_vendor_analysis_fleet(
    db: AsyncSession,
    tenant_id: int = 1,
) -> VendorFleetResponse:
    vendor_stats = (
        await db.execute(
            select(
                Vendor.id,
                Vendor.name,
                func.coalesce(func.sum(MaintenanceEvent.total_cost), 0).label("spend"),
                func.count(MaintenanceEvent.id).label("events"),
                func.count(func.distinct(MaintenanceEvent.truck_id)).label("trucks"),
            )
            .join(MaintenanceEvent, MaintenanceEvent.vendor_id == Vendor.id, isouter=True)
            .where(Vendor.tenant_id == tenant_id, Vendor.vendor_type == "service")
            .group_by(Vendor.id, Vendor.name)
            .order_by(func.sum(MaintenanceEvent.total_cost).desc().nullslast())
        )
    ).all()

    items: list[VendorFleetItem] = []
    total_spend = Decimal("0")
    for row in vendor_stats:
        spend = Decimal(str(row.spend or 0))
        total_spend += spend
        top_cat = (
            await db.execute(
                select(MaintenanceEvent.category)
                .where(MaintenanceEvent.vendor_id == row.id)
                .group_by(MaintenanceEvent.category)
                .order_by(func.count().desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        events = row.events or 0
        items.append(
            VendorFleetItem(
                id=str(row.id),
                name=row.name,
                total_spend=spend,
                event_count=events,
                truck_count=row.trucks or 0,
                avg_cost=spend / events if events else Decimal("0"),
                top_category=top_cat,
            )
        )

    top_pct = float(items[0].total_spend / total_spend * 100) if items and total_spend else 0
    top3 = sum(float(i.total_spend) for i in items[:3])
    top3_pct = top3 / float(total_spend) * 100 if total_spend else 0

    return VendorFleetResponse(
        vendors=items,
        concentration=VendorConcentration(
            top_vendor_pct=round(top_pct, 1),
            top_3_pct=round(top3_pct, 1),
            total_vendors=len(items),
        ),
    )


async def get_vendor_analysis_detail(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    tenant_id: int = 1,
) -> VendorDetailResponse:
    vendor = (
        await db.execute(select(Vendor).where(Vendor.id == vendor_id, Vendor.tenant_id == tenant_id))
    ).scalar_one()

    events = (
        await db.execute(
            select(MaintenanceEvent)
            .where(MaintenanceEvent.vendor_id == vendor_id, MaintenanceEvent.tenant_id == tenant_id)
            .order_by(MaintenanceEvent.service_date)
        )
    ).scalars().all()

    total_spend = sum((e.total_cost for e in events), Decimal("0"))
    event_count = len(events)
    avg_cost = total_spend / event_count if event_count else Decimal("0")

    by_truck_map: dict[uuid.UUID, list[MaintenanceEvent]] = {}
    for e in events:
        by_truck_map.setdefault(e.truck_id, []).append(e)

    by_truck: list[VendorByTruck] = []
    for tid, evts in by_truck_map.items():
        unit = (await db.execute(select(Truck.unit_number).where(Truck.id == tid))).scalar_one()
        by_truck.append(
            VendorByTruck(
                truck_unit=unit,
                count=len(evts),
                total_spend=sum(x.total_cost for x in evts),
            )
        )

    by_cat_map: dict[str, list[MaintenanceEvent]] = {}
    for e in events:
        by_cat_map.setdefault(e.category, []).append(e)
    by_category = [
        VendorByCategory(category=cat, count=len(evts), total_spend=sum(x.total_cost for x in evts))
        for cat, evts in by_cat_map.items()
    ]

    monthly: dict[str, list[MaintenanceEvent]] = {}
    for e in events:
        monthly.setdefault(e.service_date.strftime("%Y-%m"), []).append(e)
    trend = [
        VendorTrendPoint(month=m, spend=sum(x.total_cost for x in evts), count=len(evts))
        for m, evts in sorted(monthly.items())
    ]

    fleet_avg = (
        await db.execute(
            select(func.avg(MaintenanceEvent.total_cost)).where(MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalar_one() or Decimal("0")
    diff = 0.0
    if float(fleet_avg) > 0:
        diff = round((float(avg_cost) - float(fleet_avg)) / float(fleet_avg) * 100, 1)

    return VendorDetailResponse(
        vendor=VendorDetailInfo(name=vendor.name, address=vendor.address, type=vendor.vendor_type),
        summary=VendorSummary(
            total_spend=total_spend,
            event_count=event_count,
            avg_cost=avg_cost,
            first_visit=events[0].service_date if events else None,
            last_visit=events[-1].service_date if events else None,
        ),
        by_truck=sorted(by_truck, key=lambda x: x.total_spend, reverse=True),
        by_category=sorted(by_category, key=lambda x: x.total_spend, reverse=True),
        trend=trend,
        comparison=VendorCostComparison(
            vendor_avg_cost=avg_cost,
            fleet_avg_cost=Decimal(str(fleet_avg)),
            difference_pct=diff,
        ),
    )
