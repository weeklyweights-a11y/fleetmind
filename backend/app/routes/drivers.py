"""Driver API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._lookup import resolve_driver_id
from app.agents.driver_profile import get_driver_profile
from app.database import get_db
from app.models.assignment import Assignment
from app.models.driver import Driver
from app.models.truck import Truck
from app.schemas.drivers import DriverListItem, DriverProfileResponse
from app.schemas.pagination import PaginatedResponse, build_paginated, paginate_params

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


@router.get("", response_model=PaginatedResponse[DriverListItem])
async def list_drivers(
    status: str | None = None,
    assignment: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    sort_by: str = "full_name",
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[DriverListItem]:
    page, per_page, offset = paginate_params(page, per_page)
    query = select(Driver).where(Driver.tenant_id == 1)
    count_q = select(func.count()).select_from(Driver).where(Driver.tenant_id == 1)
    if status:
        query = query.where(Driver.status == status)
        count_q = count_q.where(Driver.status == status)

    total = (await db.execute(count_q)).scalar_one()
    sort_col = getattr(Driver, sort_by if sort_by in {"full_name", "driver_code", "license_expiry_date"} else "full_name")
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    drivers = (await db.execute(query.limit(per_page).offset(offset))).scalars().all()

    assigned_ids = set(
        (await db.execute(select(Assignment.driver_id).where(Assignment.end_date.is_(None)))).scalars().all()
    )

    items: list[DriverListItem] = []
    for driver in drivers:
        if assignment == "assigned" and driver.id not in assigned_ids:
            continue
        if assignment == "unassigned" and driver.id in assigned_ids:
            continue
        truck_unit = None
        if driver.id in assigned_ids:
            row = (
                await db.execute(
                    select(Truck.unit_number)
                    .join(Assignment, Assignment.truck_id == Truck.id)
                    .where(Assignment.driver_id == driver.id, Assignment.end_date.is_(None))
                    .limit(1)
                )
            ).scalar_one_or_none()
            truck_unit = row
        items.append(
            DriverListItem(
                id=driver.id,
                driver_code=driver.driver_code,
                full_name=driver.full_name,
                status=driver.status,
                current_truck_unit=truck_unit,
                license_expiry_date=driver.license_expiry_date,
            )
        )

    return build_paginated(items, total, page, per_page)


@router.get("/{id}", response_model=DriverProfileResponse)
async def driver_profile(
    id: str,
    code: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> DriverProfileResponse:
    driver_id = await resolve_driver_id(db, identifier=id, code=code)
    return await get_driver_profile(db, driver_id)
