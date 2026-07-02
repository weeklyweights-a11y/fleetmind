"""Truck financials sub-agent."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._fleet_stats import percentile_rank, safe_mean
from app.models.ifta import IFTAVehicleDetail
from app.models.maintenance_event import MaintenanceEvent
from app.models.mileage_record import MileageRecord
from app.models.registration import Registration
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.schemas.trucks import (
    AcquisitionInfo,
    BookValue,
    CostBreakdown,
    FleetFinancialComparison,
    ProfitabilityEstimate,
    TruckFinancialsResponse,
)


async def get_truck_financials(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckFinancialsResponse:
    truck = (
        await db.execute(select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id))
    ).scalar_one()

    maintenance_total = (
        await db.execute(
            select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                MaintenanceEvent.truck_id == truck_id, MaintenanceEvent.tenant_id == tenant_id
            )
        )
    ).scalar_one() or Decimal("0")

    registration_total = (
        await db.execute(
            select(func.coalesce(func.sum(Registration.total_fees_paid), 0)).where(
                Registration.truck_id == truck_id, Registration.tenant_id == tenant_id
            )
        )
    ).scalar_one() or Decimal("0")

    acquisition = truck.purchase_price or Decimal("0")
    insurance_total: Decimal | None = None
    tco = acquisition + Decimal(str(maintenance_total)) + Decimal(str(registration_total))
    if insurance_total:
        tco += insurance_total

    total = float(tco) if tco else 1.0
    cost_breakdown = CostBreakdown(
        acquisition_pct=round(float(acquisition) / total * 100, 1),
        maintenance_pct=round(float(maintenance_total) / total * 100, 1),
        registration_pct=round(float(registration_total) / total * 100, 1),
        insurance_pct=0.0,
    )

    mileage = (
        await db.execute(
            select(MileageRecord)
            .where(MileageRecord.truck_id == truck_id, MileageRecord.tenant_id == tenant_id)
            .order_by(MileageRecord.record_date)
        )
    ).scalars().all()

    total_miles: int | None = None
    cost_per_mile: Decimal | None = None
    if len(mileage) >= 2:
        total_miles = mileage[-1].odometer_reading - mileage[0].odometer_reading
        if total_miles > 0:
            cost_per_mile = tco / total_miles

    months_owned = 1
    if truck.acquired_date:
        months_owned = max(1, (date.today() - truck.acquired_date).days // 30)
    monthly_cost_rate = Decimal(str(maintenance_total)) / months_owned

    years_owned = 0.0
    if truck.acquired_date:
        years_owned = (date.today() - truck.acquired_date).days / 365.25
    depreciated = max(Decimal("0"), acquisition - acquisition * Decimal(str(years_owned / 10)))

    seller: str | None = None
    if truck.acquired_from_vendor_id:
        seller = (
            await db.execute(select(Vendor.name).where(Vendor.id == truck.acquired_from_vendor_id))
        ).scalar_one_or_none()

    active_trucks = (
        await db.execute(select(Truck).where(Truck.tenant_id == tenant_id, Truck.status == "active"))
    ).scalars().all()

    tco_values: list[float] = []
    cpm_values: list[float] = []
    for t in active_trucks:
        m = (
            await db.execute(
                select(func.coalesce(func.sum(MaintenanceEvent.total_cost), 0)).where(
                    MaintenanceEvent.truck_id == t.id
                )
            )
        ).scalar_one() or 0
        r = (
            await db.execute(
                select(func.coalesce(func.sum(Registration.total_fees_paid), 0)).where(
                    Registration.truck_id == t.id
                )
            )
        ).scalar_one() or 0
        tco_val = float((t.purchase_price or 0) + Decimal(str(m)) + Decimal(str(r)))
        tco_values.append(tco_val)

        miles_rows = (
            await db.execute(
                select(MileageRecord)
                .where(MileageRecord.truck_id == t.id)
                .order_by(MileageRecord.record_date)
            )
        ).scalars().all()
        if len(miles_rows) >= 2:
            miles = miles_rows[-1].odometer_reading - miles_rows[0].odometer_reading
            if miles > 0:
                cpm_values.append(tco_val / miles)

    fleet_avg_tco = Decimal(str(safe_mean(tco_values)))
    rank = percentile_rank(float(tco), tco_values)
    fleet_avg_cpm = Decimal(str(safe_mean(cpm_values))) if cpm_values else None
    cpm_rank = percentile_rank(float(cost_per_mile), cpm_values) if cost_per_mile and cpm_values else None

    profitability: ProfitabilityEstimate | None = None
    ifta_miles = (
        await db.execute(
            select(func.coalesce(func.sum(IFTAVehicleDetail.miles), 0)).where(
                IFTAVehicleDetail.truck_id == truck_id, IFTAVehicleDetail.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    if ifta_miles and int(ifta_miles) > 0:
        rpm = Decimal("2.75")
        est_rev = rpm * int(ifta_miles)
        margin = est_rev - tco
        profitability = ProfitabilityEstimate(
            revenue_per_mile=rpm,
            estimated_revenue=est_rev,
            margin=margin,
        )

    return TruckFinancialsResponse(
        acquisition=AcquisitionInfo(
            price=truck.purchase_price,
            acquisition_date=truck.acquired_date,
            seller=seller,
            initial_odometer=truck.initial_odometer,
        ),
        maintenance_total=Decimal(str(maintenance_total)),
        registration_total=Decimal(str(registration_total)),
        insurance_total=insurance_total,
        total_cost_of_ownership=tco,
        cost_breakdown=cost_breakdown,
        cost_per_mile=cost_per_mile,
        monthly_cost_rate=monthly_cost_rate,
        book_value=BookValue(
            original=acquisition,
            depreciated=depreciated,
            years_owned=round(years_owned, 2),
        ),
        fleet_comparison=FleetFinancialComparison(
            fleet_avg_tco=fleet_avg_tco,
            rank=rank,
            fleet_avg_cost_per_mile=fleet_avg_cpm,
            cost_per_mile_rank=cpm_rank,
        ),
        total_miles_driven=total_miles,
        profitability_estimate=profitability,
    )
