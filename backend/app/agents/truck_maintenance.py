"""Truck maintenance sub-agent."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._fleet_stats import percentile_rank, safe_mean
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.neo4j_client import get_neo4j_driver
from app.schemas.trucks import (
    CategoryBreakdown,
    FleetMaintenanceComparison,
    LastService,
    MaintenancePattern,
    MaintenanceSummary,
    MaintenanceTrendPoint,
    TruckMaintenanceResponse,
    VendorBreakdown,
)


async def get_truck_maintenance(
    db: AsyncSession,
    truck_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    include_trend: bool = False,
    tenant_id: int = 1,
) -> TruckMaintenanceResponse:
    base_filter = [
        MaintenanceEvent.truck_id == truck_id,
        MaintenanceEvent.tenant_id == tenant_id,
    ]
    if start_date:
        base_filter.append(MaintenanceEvent.service_date >= start_date)
    if end_date:
        base_filter.append(MaintenanceEvent.service_date <= end_date)

    events = (
        await db.execute(select(MaintenanceEvent).where(*base_filter).order_by(MaintenanceEvent.service_date.desc()))
    ).scalars().all()

    total_spend = sum((e.total_cost for e in events), Decimal("0"))
    event_count = len(events)
    avg_cost = total_spend / event_count if event_count else Decimal("0")
    costs = [e.total_cost for e in events]
    min_cost = min(costs) if costs else Decimal("0")
    max_cost = max(costs) if costs else Decimal("0")

    last_service: LastService | None = None
    if events:
        e = events[0]
        vname = (
            await db.execute(select(Vendor.name).where(Vendor.id == e.vendor_id))
        ).scalar_one_or_none() or "Unknown"
        last_service = LastService(
            service_date=e.service_date,
            vendor_name=vname,
            category=e.category,
            description=e.description[:200],
            cost=e.total_cost,
            days_ago=(date.today() - e.service_date).days,
        )

    by_cat: dict[str, list[MaintenanceEvent]] = {}
    for e in events:
        by_cat.setdefault(e.category, []).append(e)

    by_category = sorted(
        [
            CategoryBreakdown(
                category=cat,
                count=len(evts),
                total_spend=sum(x.total_cost for x in evts),
                pct_of_total=float(sum(x.total_cost for x in evts) / total_spend * 100) if total_spend else 0,
            )
            for cat, evts in by_cat.items()
        ],
        key=lambda x: x.total_spend,
        reverse=True,
    )

    by_vend: dict[uuid.UUID, list[MaintenanceEvent]] = {}
    for e in events:
        by_vend.setdefault(e.vendor_id, []).append(e)

    vendor_breakdowns: list[VendorBreakdown] = []
    for vid, evts in by_vend.items():
        vname = (await db.execute(select(Vendor.name).where(Vendor.id == vid))).scalar_one_or_none() or "Unknown"
        vendor_breakdowns.append(
            VendorBreakdown(
                vendor_name=vname,
                count=len(evts),
                total_spend=sum(x.total_cost for x in evts),
                avg_cost=sum(x.total_cost for x in evts) / len(evts),
                last_visit=max(x.service_date for x in evts),
            )
        )
    by_vendor = sorted(vendor_breakdowns, key=lambda x: x.total_spend, reverse=True)

    active_trucks = (
        await db.execute(select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.status == "active"))
    ).scalars().all()

    truck_totals: list[float] = []
    for tid in active_trucks:
        tsum = (
            await db.execute(
                select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                    MaintenanceEvent.truck_id == tid, MaintenanceEvent.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        truck_totals.append(float(tsum))

    fleet_avg = Decimal(str(safe_mean(truck_totals)))
    ratio = float(total_spend / fleet_avg) if fleet_avg else 0.0
    rank = percentile_rank(float(total_spend), truck_totals)

    all_events_count = (
        await db.execute(
            select(func.count()).select_from(MaintenanceEvent).where(MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalar_one() or 0
    fleet_avg_per_event = Decimal("0")
    if all_events_count:
        fleet_total = (
            await db.execute(
                select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                    MaintenanceEvent.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        fleet_avg_per_event = Decimal(str(fleet_total)) / all_events_count

    trend: list[MaintenanceTrendPoint] = []
    if include_trend:
        monthly: dict[str, list[MaintenanceEvent]] = {}
        for e in events:
            key = e.service_date.strftime("%Y-%m")
            monthly.setdefault(key, []).append(e)
        for month in sorted(monthly.keys()):
            evts = monthly[month]
            trend.append(
                MaintenanceTrendPoint(
                    month=month,
                    total_spend=sum(x.total_cost for x in evts),
                    event_count=len(evts),
                )
            )

    patterns: list[MaintenancePattern] = []
    six_months_ago = date.today() - timedelta(days=180)
    for cat, evts in by_cat.items():
        recent = [e for e in evts if e.service_date >= six_months_ago]
        if len(recent) >= 3:
            patterns.append(
                MaintenancePattern(
                    pattern_type="recurring_issue",
                    description=f"{len(recent)} {cat} events in last 6 months",
                    supporting_data={"category": cat, "count": len(recent)},
                )
            )

    vendor_graph: dict = {"nodes": [], "edges": []}
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Truck {pg_id: $truck_id})-[r:MAINTAINED_AT]->(v:Vendor)
                RETURN v.pg_id AS vid, count(r) AS visits
                """,
                truck_id=str(truck_id),
            )
            async for record in result:
                vendor_graph["edges"].append(
                    {"source": str(truck_id), "target": str(record["vid"]), "visits": record["visits"]}
                )
    except Exception:
        pass

    return TruckMaintenanceResponse(
        summary=MaintenanceSummary(
            total_spend=total_spend,
            event_count=event_count,
            avg_cost=avg_cost,
            min_cost=min_cost,
            max_cost=max_cost,
        ),
        last_service=last_service,
        by_category=by_category,
        by_vendor=by_vendor,
        fleet_comparison=FleetMaintenanceComparison(
            fleet_avg_total=fleet_avg,
            this_truck_total=total_spend,
            ratio=ratio,
            rank_in_fleet=rank,
            fleet_avg_per_event=fleet_avg_per_event,
            fleet_avg_frequency=float(all_events_count / len(active_trucks)) if active_trucks else 0,
        ),
        trend=trend,
        patterns=patterns,
        vendor_graph=vendor_graph,
    )
