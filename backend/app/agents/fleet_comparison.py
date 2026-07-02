"""Fleet comparison sub-agent."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import build_compliance_matrix, rollup_compliance_status
from app.agents._fleet_stats import detect_outliers, rank_desc, safe_mean
from app.agents._parallel import gather_limited, run_with_session
from app.agents.truck_financials import get_truck_financials
from app.agents.truck_maintenance import get_truck_maintenance
from app.models.assignment import Assignment
from app.models.driver import Driver
from app.models.truck import Truck
from app.schemas.fleet import (
    FleetAverages,
    FleetComparisonRankings,
    FleetComparisonResponse,
    FleetComparisonTruck,
)


async def _comparison_for_truck(truck_id: uuid.UUID, tenant_id: int) -> FleetComparisonTruck:
    async def _inner(db: AsyncSession) -> FleetComparisonTruck:
        truck = (
            await db.execute(select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id))
        ).scalar_one()
        financials = await get_truck_financials(db, truck_id, tenant_id)
        maintenance = await get_truck_maintenance(db, truck_id, tenant_id=tenant_id)

        matrix, _, _ = await build_compliance_matrix(db, tenant_id)
        row = next((r for r in matrix if r.truck_unit == truck.unit_number), None)
        compliance_status = "incomplete"
        if row:
            statuses = [
                row.insurance.status,
                row.registration.status,
                row.title.status,
                row.emission.status,
                row.driver_cdl.status,
                row.medical_cert.status,
            ]
            compliance_status = rollup_compliance_status(statuses)

        driver_name = (
            await db.execute(
                select(Driver.full_name)
                .join(Assignment, Assignment.driver_id == Driver.id)
                .where(Assignment.truck_id == truck_id, Assignment.end_date.is_(None))
                .order_by(Assignment.start_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        top_cat = maintenance.by_category[0].category if maintenance.by_category else None
        age = date.today().year - truck.year if truck.year else 0

        return FleetComparisonTruck(
            truck_id=truck.id,
            unit_number=truck.unit_number,
            make_model_year=f"{truck.year} {truck.make} {truck.model}",
            driver_name=driver_name,
            tco=financials.total_cost_of_ownership,
            maintenance_spend=financials.maintenance_total,
            event_count=maintenance.summary.event_count,
            cost_per_mile=financials.cost_per_mile,
            top_category=top_cat,
            compliance_status=compliance_status,
            age_years=float(age),
        )

    return await run_with_session(_inner)


async def get_fleet_comparison(
    db: AsyncSession,
    truck_ids: list[uuid.UUID] | None = None,
    tenant_id: int = 1,
) -> FleetComparisonResponse:
    if truck_ids:
        ids = truck_ids
    else:
        ids = list(
            (
                await db.execute(
                    select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.status == "active")
                )
            ).scalars().all()
        )

    trucks: list[FleetComparisonTruck] = await gather_limited(
        *[_comparison_for_truck(tid, tenant_id) for tid in ids]
    )

    tco_map = {t.unit_number: float(t.tco) for t in trucks}
    maint_map = {t.unit_number: float(t.maintenance_spend) for t in trucks}
    cpm_map = {t.unit_number: float(t.cost_per_mile) for t in trucks if t.cost_per_mile}

    for t in trucks:
        flags: list[str] = []
        if t.unit_number in detect_outliers(tco_map):
            flags.append("tco_outlier")
        if t.unit_number in detect_outliers(maint_map):
            flags.append("maintenance_outlier")
        if t.cost_per_mile and t.unit_number in detect_outliers(cpm_map):
            flags.append("cost_per_mile_outlier")
        t.outlier_flags = flags

    rankings = FleetComparisonRankings(
        by_tco=rank_desc([(t.unit_number, float(t.tco)) for t in trucks]),
        by_maintenance=rank_desc([(t.unit_number, float(t.maintenance_spend)) for t in trucks]),
        by_cost_per_mile=rank_desc(
            [(t.unit_number, float(t.cost_per_mile)) for t in trucks if t.cost_per_mile]
        ),
    )

    averages = FleetAverages(
        avg_tco=Decimal(str(safe_mean([float(t.tco) for t in trucks]))),
        avg_maintenance=Decimal(str(safe_mean([float(t.maintenance_spend) for t in trucks]))),
        avg_events=safe_mean([float(t.event_count) for t in trucks]),
        avg_cost_per_mile=Decimal(str(safe_mean([float(t.cost_per_mile) for t in trucks if t.cost_per_mile])))
        if any(t.cost_per_mile for t in trucks)
        else None,
    )

    trucks.sort(key=lambda x: x.tco, reverse=True)
    return FleetComparisonResponse(trucks=trucks, rankings=rankings, fleet_averages=averages)
