"""Entity resolution before normalized writes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DocumentType, TruckStatus
from app.models.driver import Driver
from app.models.truck import Truck
from app.models.vendor import Vendor


@dataclass
class ResolvedEntities:
    truck: Truck | None = None
    driver: Driver | None = None
    vendor: Vendor | None = None
    truck_confidence: float = 0.0
    driver_confidence: float = 0.0
    vendor_confidence: float = 0.0
    create_truck: bool = False
    create_driver: bool = False
    needs_review: bool = False


async def resolve_truck(
    db: AsyncSession,
    fields: dict,
    document_type: str,
    tenant_id: int = 1,
    for_update: bool = False,
    allow_infer: bool = False,
) -> tuple[Truck | None, float, bool]:
    vin = fields.get("vin")
    unit = fields.get("unit_number") or fields.get("fleet_unit_no")

    if vin:
        q = select(Truck).where(Truck.tenant_id == tenant_id, Truck.vin == str(vin))
        if for_update:
            q = q.with_for_update()
        truck = (await db.execute(q)).scalars().first()
        if truck:
            return truck, 1.0, False

    if unit is not None:
        try:
            unit_int = int(unit)
        except (TypeError, ValueError):
            unit_int = None
        if unit_int is not None:
            q = select(Truck).where(Truck.tenant_id == tenant_id, Truck.unit_number == unit_int)
            if for_update:
                q = q.with_for_update()
            truck = (await db.execute(q)).scalars().first()
            if truck:
                return truck, 0.85, False

    if document_type == DocumentType.BILL_OF_SALE_PURCHASE.value:
        return None, 1.0, True

    if allow_infer and vin and unit is not None:
        try:
            unit_int = int(unit)
        except (TypeError, ValueError):
            return None, 0.0, False
        year_raw = fields.get("year")
        try:
            year = int(year_raw) if year_raw is not None else 2000
        except (TypeError, ValueError):
            year = 2000
        truck = Truck(
            id=uuid.uuid4(),
            unit_number=unit_int,
            vin=str(vin),
            year=year,
            make=str(fields.get("make") or "Unknown"),
            model=str(fields.get("model") or "Unknown"),
            body_type=fields.get("body_type"),
            color=fields.get("color"),
            status=TruckStatus.ACTIVE.value,
            tenant_id=tenant_id,
        )
        db.add(truck)
        await db.flush()
        return truck, 0.5, True

    return None, 0.0, False


async def resolve_driver(
    db: AsyncSession,
    fields: dict,
    document_type: str,
    tenant_id: int = 1,
) -> tuple[Driver | None, float, bool]:
    license_number = fields.get("license_number")
    driver_code = fields.get("driver_code")
    full_name = fields.get("full_name")

    if license_number:
        driver = (
            await db.execute(
                select(Driver).where(
                    Driver.tenant_id == tenant_id,
                    Driver.license_number == str(license_number),
                ).limit(1)
            )
        ).scalars().first()
        if driver:
            return driver, 1.0, False

    if driver_code:
        driver = (
            await db.execute(
                select(Driver).where(
                    Driver.tenant_id == tenant_id,
                    Driver.driver_code == str(driver_code),
                ).limit(1)
            )
        ).scalars().first()
        if driver:
            return driver, 0.9, False

    if full_name:
        driver = (
            await db.execute(
                select(Driver).where(
                    Driver.tenant_id == tenant_id,
                    func.lower(Driver.full_name) == str(full_name).lower(),
                ).limit(1)
            )
        ).scalars().first()
        if driver:
            return driver, 0.75, False

    if document_type == DocumentType.CDL.value:
        return None, 1.0, True

    return None, 0.0, False


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


async def resolve_vendor(
    db: AsyncSession,
    name: str,
    address: str | None,
    vendor_type: str,
    tenant_id: int = 1,
) -> tuple[Vendor, float]:
    name = _normalize_name(name)
    address = (address or "").strip() or None
    q = select(Vendor).where(
        Vendor.tenant_id == tenant_id,
        func.lower(Vendor.name) == name.lower(),
    )
    if address:
        q = q.where(func.coalesce(Vendor.address, "") == address)
    q = q.order_by(Vendor.created_at).limit(1)
    vendor = (await db.execute(q)).scalars().first()
    if vendor:
        return vendor, 1.0
    vendor = Vendor(
        id=uuid.uuid4(),
        name=name,
        address=address,
        vendor_type=vendor_type,
        tenant_id=tenant_id,
    )
    db.add(vendor)
    await db.flush()
    return vendor, 0.95
