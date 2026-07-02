"""Graph API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph_queries import get_entity_connections
from app.database import get_db
from app.schemas.graph import EntityConnectionsResponse

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/connections", response_model=EntityConnectionsResponse)
async def entity_connections(
    type: str = Query(..., alias="type"),
    id: str = Query(..., alias="id"),
    hops: int = Query(2, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
) -> EntityConnectionsResponse:
    return await get_entity_connections(db, type, id, hops)
