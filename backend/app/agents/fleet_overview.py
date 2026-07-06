"""Fleet overview sub-agent."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import compliance_snapshot_counts
from app.agents.truck_financials import get_truck_financials
from app.models.assignment import Assignment
from app.models.document import Document
from app.models.driver import Driver
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.services.activity_description import build_activity_description
from app.schemas.fleet import (
    ComplianceSnapshot,
    FinancialSnapshot,
    FleetComposition,
    FleetOverviewResponse,
    QuickStats,
    RecentActivityItem,
)


async def get_fleet_overview(
    db: AsyncSession,
    tenant_id: int = 1,
) -> FleetOverviewResponse:
    today = date.today()
    month_start = today.replace(day=1)

    trucks = (
        await db.execute(select(Truck).where(Truck.tenant_id == tenant_id))
    ).scalars().all()
    drivers = (
        await db.execute(select(Driver).where(Driver.tenant_id == tenant_id))
    ).scalars().all()

    active = sum(1 for t in trucks if t.status == "active")
    sold = sum(1 for t in trucks if t.status == "sold")
    inactive = sum(1 for t in trucks if t.status == "inactive")

    assigned_driver_ids = set(
        (
            await db.execute(
                select(Assignment.driver_id).where(
                    Assignment.tenant_id == tenant_id, Assignment.end_date.is_(None)
                )
            )
        ).scalars().all()
    )
    assigned = len(assigned_driver_ids)
    unassigned = len(drivers) - assigned

    fleet_value = sum((t.purchase_price or Decimal("0") for t in trucks if t.status == "active"), Decimal("0"))
    ages = [today.year - t.year for t in trucks if t.status == "active" and t.year]
    avg_age = sum(ages) / len(ages) if ages else 0.0

    fully, warnings, expirations, incomplete, urgent_legacy = await compliance_snapshot_counts(db, tenant_id)

    from app.intelligence.jobs.compliance_scanner import read_compliance_cache

    cache = await read_compliance_cache(tenant_id=tenant_id)
    if cache and cache.get("urgent_items"):
        urgent = cache["urgent_items"]
    else:
        urgent = urgent_legacy

    this_month = (
        await db.execute(
            select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= month_start,
            )
        )
    ).scalar_one() or Decimal("0")

    if month_start.month == 1:
        last_month_start = date(month_start.year - 1, 12, 1)
    else:
        last_month_start = date(month_start.year, month_start.month - 1, 1)
    last_month_end = month_start

    last_month = (
        await db.execute(
            select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= last_month_start,
                MaintenanceEvent.service_date < last_month_end,
            )
        )
    ).scalar_one() or Decimal("0")

    three_month_avg = Decimal(str(this_month))  # simplified; could expand to 3-month window
    mom = None
    if float(last_month) > 0:
        mom = round((float(this_month) - float(last_month)) / float(last_month) * 100, 1)

    total_tco = Decimal("0")
    for t in trucks:
        if t.status != "active":
            continue
        m = (
            await db.execute(
                select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                    MaintenanceEvent.truck_id == t.id
                )
            )
        ).scalar_one() or 0
        total_tco += (t.purchase_price or Decimal("0")) + Decimal(str(m))

    recent_docs = (
        await db.execute(
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    recent_activity: list[RecentActivityItem] = []
    for doc in recent_docs:
        unit = None
        if doc.truck_id:
            u = (
                await db.execute(select(Truck.unit_number).where(Truck.id == doc.truck_id))
            ).scalar_one_or_none()
            unit = u
        recent_activity.append(
            RecentActivityItem(
                document_id=doc.id,
                type=doc.document_type,
                truck_unit=unit,
                activity_date=doc.document_date,
                status=doc.processing_status,
                description=build_activity_description(doc),
                created_at=doc.created_at,
            )
        )

    review_count = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "needs_review",
            )
        )
    ).scalar_one() or 0

    maint_total = (
        await db.execute(
            select(func.count()).select_from(MaintenanceEvent).where(MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalar_one() or 0

    vendor_count = (
        await db.execute(select(func.count()).select_from(Vendor).where(Vendor.tenant_id == tenant_id))
    ).scalar_one() or 0

    month_spend_by_truck = (
        await db.execute(
            select(
                MaintenanceEvent.truck_id,
                func.coalesce(func.sum(MaintenanceEvent.total_cost), 0).label("spend"),
                func.count(MaintenanceEvent.id).label("events"),
            )
            .where(
                MaintenanceEvent.tenant_id == tenant_id,
                MaintenanceEvent.service_date >= month_start,
            )
            .group_by(MaintenanceEvent.truck_id)
        )
    ).all()
    if not month_spend_by_truck:
        month_spend_by_truck = (
            await db.execute(
                select(
                    MaintenanceEvent.truck_id,
                    func.coalesce(func.sum(MaintenanceEvent.total_cost), 0).label("spend"),
                    func.count(MaintenanceEvent.id).label("events"),
                )
                .where(MaintenanceEvent.tenant_id == tenant_id)
                .group_by(MaintenanceEvent.truck_id)
            )
        ).all()
    truck_unit_map = {t.id: t.unit_number for t in trucks}
    most_expensive = None
    most_serviced = None
    if month_spend_by_truck:
        top_spend = max(month_spend_by_truck, key=lambda r: float(r.spend))
        top_events = max(month_spend_by_truck, key=lambda r: r.events)
        most_expensive = {
            "unit": truck_unit_map.get(top_spend.truck_id),
            "total_spend": float(top_spend.spend),
        }
        most_serviced = {
            "unit": truck_unit_map.get(top_events.truck_id),
            "event_count": int(top_events.events),
        }

    cpms: list[float] = []
    for t in trucks:
        if t.status != "active":
            continue
        fin = await get_truck_financials(db, t.id, tenant_id)
        if fin.cost_per_mile is not None:
            cpms.append(float(fin.cost_per_mile))
    fleet_avg_cpm = Decimal(str(sum(cpms) / len(cpms))) if cpms else None

    return FleetOverviewResponse(
        fleet_composition=FleetComposition(
            total_trucks=len(trucks),
            active=active,
            sold=sold,
            inactive=inactive,
            total_drivers=len(drivers),
            assigned_drivers=assigned,
            unassigned_drivers=unassigned,
            total_fleet_value=fleet_value,
            avg_truck_age=round(avg_age, 1),
        ),
        compliance_snapshot=ComplianceSnapshot(
            fully_compliant=fully,
            warnings=warnings,
            expirations=expirations,
            incomplete=incomplete,
            urgent_items=urgent,
        ),
        financial_snapshot=FinancialSnapshot(
            this_month_spend=Decimal(str(this_month)),
            last_month_spend=Decimal(str(last_month)),
            three_month_avg=three_month_avg,
            mom_change_pct=mom,
            total_fleet_tco=total_tco,
        ),
        recent_activity=recent_activity,
        review_queue_count=review_count,
        quick_stats=QuickStats(
            total_maintenance_events=maint_total,
            total_vendors=vendor_count,
            most_expensive_truck=most_expensive,
            most_serviced_truck=most_serviced,
            fleet_avg_cost_per_mile=fleet_avg_cpm,
        ),
    )
