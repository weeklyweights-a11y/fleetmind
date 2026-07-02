"""Truck API routes."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import build_compliance_matrix, rollup_compliance_status
from app.agents._lookup import resolve_truck_id
from app.agents.graph_queries import get_truck_graph
from app.agents.truck_assignment import get_truck_assignment
from app.agents.truck_compliance import get_truck_compliance
from app.agents.truck_documents import get_truck_documents
from app.agents.truck_financials import get_truck_financials
from app.agents.truck_identity import get_truck_identity
from app.agents.truck_maintenance import get_truck_maintenance
from app.database import get_db
from app.models.assignment import Assignment
from app.models.driver import Driver
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck
from app.schemas.pagination import PaginatedResponse, build_paginated, paginate_params
from app.schemas.trucks import (
    TruckAssignmentResponse,
    TruckComplianceResponse,
    TruckDocumentsResponse,
    TruckFinancialsResponse,
    TruckGraphResponse,
    TruckIdentityResponse,
    TruckListItem,
    TruckMaintenanceResponse,
)

router = APIRouter(prefix="/api/trucks", tags=["trucks"])

SORT_FIELDS = {"unit_number", "year", "make", "status", "acquired_date"}


@router.get("", response_model=PaginatedResponse[TruckListItem])
async def list_trucks(
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    sort_by: str = "unit_number",
    sort_order: str = "asc",
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TruckListItem]:
    page, per_page, offset = paginate_params(page, per_page)
    query = select(Truck).where(Truck.tenant_id == 1)
    count_q = select(func.count()).select_from(Truck).where(Truck.tenant_id == 1)
    if status:
        query = query.where(Truck.status == status)
        count_q = count_q.where(Truck.status == status)
    if search:
        like = f"%{search}%"
        query = query.where((Truck.vin.ilike(like)) | (Truck.unit_number.cast(String).ilike(like)))
        count_q = count_q.where((Truck.vin.ilike(like)) | (Truck.unit_number.cast(String).ilike(like)))

    total = (await db.execute(count_q)).scalar_one()
    sort_col = getattr(Truck, sort_by if sort_by in SORT_FIELDS else "unit_number")
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    trucks = (await db.execute(query.limit(per_page).offset(offset))).scalars().all()

    matrix, _, _ = await build_compliance_matrix(db, 1)
    compliance_by_unit: dict[int, str] = {}
    for row in matrix:
        statuses = [
            row.insurance.status,
            row.registration.status,
            row.title.status,
            row.emission.status,
            row.driver_cdl.status,
            row.medical_cert.status,
        ]
        compliance_by_unit[row.truck_unit] = rollup_compliance_status(statuses)

    spend_rows = (
        await db.execute(
            select(
                MaintenanceEvent.truck_id,
                func.coalesce(func.sum(MaintenanceEvent.total_cost), 0),
            ).group_by(MaintenanceEvent.truck_id)
        )
    ).all()
    spend_map = {r[0]: Decimal(str(r[1])) for r in spend_rows}

    items: list[TruckListItem] = []
    for truck in trucks:
        driver_name = (
            await db.execute(
                select(Driver.full_name)
                .join(Assignment, Assignment.driver_id == Driver.id)
                .where(Assignment.truck_id == truck.id, Assignment.end_date.is_(None))
                .order_by(Assignment.start_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        comp = compliance_by_unit.get(truck.unit_number, "incomplete")
        comp_color = comp if comp in {"green", "yellow", "red", "grey"} else "grey"
        items.append(
            TruckListItem(
                id=truck.id,
                unit_number=truck.unit_number,
                vin=truck.vin,
                year=truck.year,
                make=truck.make,
                model=truck.model,
                status=truck.status,
                current_driver_name=driver_name,
                overall_compliance_status=comp_color,
                total_maintenance_spend=spend_map.get(truck.id, Decimal("0")),
            )
        )
    return build_paginated(items, total, page, per_page)


async def _truck_id(db: AsyncSession, id: str, unit: int | None = None) -> uuid.UUID:
    return await resolve_truck_id(db, identifier=id, unit=unit)


@router.get("/{id}", response_model=TruckIdentityResponse)
async def truck_identity(
    id: str,
    unit: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> TruckIdentityResponse:
    truck_id = await _truck_id(db, id, unit)
    return await get_truck_identity(db, truck_id)


@router.get("/{id}/assignment", response_model=TruckAssignmentResponse)
async def truck_assignment(id: str, db: AsyncSession = Depends(get_db)) -> TruckAssignmentResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_assignment(db, truck_id)


@router.get("/{id}/maintenance", response_model=TruckMaintenanceResponse)
async def truck_maintenance(
    id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    include_trend: bool = False,
    db: AsyncSession = Depends(get_db),
) -> TruckMaintenanceResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_maintenance(db, truck_id, start_date, end_date, include_trend)


@router.get("/{id}/compliance", response_model=TruckComplianceResponse)
async def truck_compliance(id: str, db: AsyncSession = Depends(get_db)) -> TruckComplianceResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_compliance(db, truck_id)


@router.get("/{id}/financials", response_model=TruckFinancialsResponse)
async def truck_financials(id: str, db: AsyncSession = Depends(get_db)) -> TruckFinancialsResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_financials(db, truck_id)


@router.get("/{id}/documents", response_model=TruckDocumentsResponse)
async def truck_documents(id: str, db: AsyncSession = Depends(get_db)) -> TruckDocumentsResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_documents(db, truck_id)


@router.get("/{id}/graph", response_model=TruckGraphResponse)
async def truck_graph(id: str, db: AsyncSession = Depends(get_db)) -> TruckGraphResponse:
    truck_id = await _truck_id(db, id)
    return await get_truck_graph(db, truck_id)
