"""Truck identity sub-agent."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import TruckNotFoundError
from app.models.mileage_record import MileageRecord
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.schemas.trucks import OdometerReading, TruckIdentityResponse


async def get_truck_identity(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckIdentityResponse:
    result = await db.execute(
        select(Truck).where(Truck.id == truck_id, Truck.tenant_id == tenant_id)
    )
    truck = result.scalar_one_or_none()
    if truck is None:
        raise TruckNotFoundError(str(truck_id))

    vendor_name: str | None = None
    if truck.acquired_from_vendor_id:
        v = await db.execute(
            select(Vendor.name).where(Vendor.id == truck.acquired_from_vendor_id)
        )
        vendor_name = v.scalar_one_or_none()

    mileage_rows = (
        await db.execute(
            select(MileageRecord)
            .where(MileageRecord.truck_id == truck_id, MileageRecord.tenant_id == tenant_id)
            .order_by(MileageRecord.record_date.desc())
        )
    ).scalars().all()

    current_odometer: OdometerReading | None = None
    estimated_miles: int | None = None
    if mileage_rows:
        latest = mileage_rows[0]
        current_odometer = OdometerReading(
            reading=latest.odometer_reading,
            record_date=latest.record_date,
            source_type=latest.source_type,
        )
        if len(mileage_rows) >= 2:
            prev = mileage_rows[1]
            days = (latest.record_date - prev.record_date).days
            if days > 0:
                daily_rate = (latest.odometer_reading - prev.odometer_reading) / days
                days_since = (date.today() - latest.record_date).days
                estimated_miles = int(latest.odometer_reading + daily_rate * days_since)

    today = date.today()
    age_years = round(today.year - truck.year + (today.month - 6) / 12, 1) if truck.year else None
    end = truck.disposed_date or today
    time_in_fleet = (end - truck.acquired_date).days if truck.acquired_date else None

    return TruckIdentityResponse(
        id=truck.id,
        unit_number=truck.unit_number,
        vin=truck.vin,
        year=truck.year,
        make=truck.make,
        model=truck.model,
        body_type=truck.body_type,
        color=truck.color,
        fuel_type=truck.fuel_type,
        gross_vehicle_weight=truck.gross_vehicle_weight,
        status=truck.status,
        acquired_date=truck.acquired_date,
        purchase_price=truck.purchase_price,
        acquired_from_vendor=vendor_name,
        initial_odometer=truck.initial_odometer,
        disposed_date=truck.disposed_date,
        sale_price=truck.sale_price,
        disposed_to=truck.disposed_to,
        disposal_type=truck.disposal_type,
        current_odometer=current_odometer,
        estimated_current_miles=estimated_miles,
        age_years=age_years,
        time_in_fleet_days=time_in_fleet,
    )
