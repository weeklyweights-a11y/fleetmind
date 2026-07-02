"""Fleet API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._lookup import resolve_truck_ids_from_list
from app.agents.fleet_comparison import get_fleet_comparison
from app.agents.fleet_overview import get_fleet_overview
from app.agents.graph_queries import get_fleet_graph
from app.database import get_db
from app.schemas.fleet import FleetComparisonResponse, FleetGraphResponse, FleetOverviewResponse

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/overview", response_model=FleetOverviewResponse)
async def fleet_overview(db: AsyncSession = Depends(get_db)) -> FleetOverviewResponse:
    return await get_fleet_overview(db)


@router.get("/comparison", response_model=FleetComparisonResponse)
async def fleet_comparison(
    trucks: str | None = Query(None, description="Comma-separated unit numbers or UUIDs"),
    db: AsyncSession = Depends(get_db),
) -> FleetComparisonResponse:
    truck_ids = None
    if trucks:
        ids = [t.strip() for t in trucks.split(",") if t.strip()]
        truck_ids = await resolve_truck_ids_from_list(db, ids)
    return await get_fleet_comparison(db, truck_ids)


@router.get("/graph", response_model=FleetGraphResponse)
async def fleet_graph(db: AsyncSession = Depends(get_db)) -> FleetGraphResponse:
    return await get_fleet_graph(db)
