"""Resolve domain identifiers to UUIDs."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DriverNotFoundError, TruckNotFoundError, VendorNotFoundError
from app.models.driver import Driver
from app.models.truck import Truck
from app.models.vendor import Vendor


async def resolve_truck_id(
    db: AsyncSession,
    identifier: str | None = None,
    unit: int | None = None,
    tenant_id: int = 1,
) -> uuid.UUID:
    if unit is not None:
        result = await db.execute(
            select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.unit_number == unit)
        )
        truck_id = result.scalar_one_or_none()
        if truck_id is None:
            raise TruckNotFoundError(str(unit))
        return truck_id

    if not identifier:
        raise TruckNotFoundError("")

    try:
        return uuid.UUID(identifier)
    except ValueError:
        pass

    if identifier.isdigit():
        result = await db.execute(
            select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.unit_number == int(identifier))
        )
        truck_id = result.scalar_one_or_none()
        if truck_id is None:
            raise TruckNotFoundError(identifier)
        return truck_id

    raise TruckNotFoundError(identifier)


async def resolve_driver_id(
    db: AsyncSession,
    identifier: str | None = None,
    code: str | None = None,
    tenant_id: int = 1,
) -> uuid.UUID:
    lookup = code or identifier
    if not lookup:
        raise DriverNotFoundError("")

    try:
        return uuid.UUID(lookup)
    except ValueError:
        pass

    result = await db.execute(
        select(Driver.id).where(Driver.tenant_id == tenant_id, Driver.driver_code == lookup)
    )
    driver_id = result.scalar_one_or_none()
    if driver_id is None:
        raise DriverNotFoundError(lookup)
    return driver_id


async def resolve_vendor_id(
    db: AsyncSession,
    identifier: str,
    tenant_id: int = 1,
) -> uuid.UUID:
    try:
        vendor_id = uuid.UUID(identifier)
    except ValueError as exc:
        raise VendorNotFoundError(identifier) from exc

    result = await db.execute(
        select(Vendor.id).where(Vendor.tenant_id == tenant_id, Vendor.id == vendor_id)
    )
    if result.scalar_one_or_none() is None:
        raise VendorNotFoundError(identifier)
    return vendor_id


async def resolve_truck_ids_from_list(
    db: AsyncSession,
    identifiers: list[str],
    tenant_id: int = 1,
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for ident in identifiers:
        ident = ident.strip()
        if not ident:
            continue
        ids.append(await resolve_truck_id(db, identifier=ident, tenant_id=tenant_id))
    return ids


async def resolve_vendor_by_name(
    db: AsyncSession,
    name: str,
    tenant_id: int = 1,
) -> uuid.UUID:
    q = name.strip()
    if not q:
        raise VendorNotFoundError(name)
    result = await db.execute(
        select(Vendor)
        .where(Vendor.tenant_id == tenant_id, Vendor.name.ilike(f"%{q}%"))
        .order_by(Vendor.name)
        .limit(2)
    )
    rows = result.scalars().all()
    if not rows:
        raise VendorNotFoundError(name)
    if len(rows) > 1 and rows[0].name.lower() != q.lower():
        raise VendorNotFoundError(f"Multiple vendors match '{name}'")
    return rows[0].id


async def resolve_driver_by_name(
    db: AsyncSession,
    name: str,
    tenant_id: int = 1,
) -> uuid.UUID:
    q = name.strip()
    if not q:
        raise DriverNotFoundError(name)
    result = await db.execute(
        select(Driver.id).where(
            Driver.tenant_id == tenant_id,
            Driver.full_name.ilike(f"%{q}%"),
        )
    )
    driver_id = result.scalar_one_or_none()
    if driver_id is None:
        raise DriverNotFoundError(name)
    return driver_id


async def resolve_truck_by_attributes(
    db: AsyncSession,
    make: str | None = None,
    color: str | None = None,
    tenant_id: int = 1,
) -> uuid.UUID:
    stmt = select(Truck).where(Truck.tenant_id == tenant_id)
    if make:
        stmt = stmt.where(Truck.make.ilike(f"%{make.strip()}%"))
    if color:
        stmt = stmt.where(Truck.color.ilike(f"%{color.strip()}%"))
    rows = (await db.execute(stmt.limit(5))).scalars().all()
    if not rows:
        raise TruckNotFoundError(f"{make or ''} {color or ''}".strip())
    if len(rows) > 1:
        raise TruckNotFoundError("Multiple trucks match description")
    return rows[0].id
