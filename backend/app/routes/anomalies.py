"""Anomaly API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.anomaly_actions import update_anomaly_status
from app.agents.anomaly_feed import get_anomaly_feed
from app.database import get_db
from app.schemas.anomalies import AnomalyFeedResponse, AnomalyItem, AnomalyStatusUpdate

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


@router.get("", response_model=AnomalyFeedResponse)
async def anomaly_feed(
    status: str | None = Query(None, description="Comma-separated statuses"),
    severity: str | None = Query(None, description="Comma-separated severities"),
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    follow_up: bool | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> AnomalyFeedResponse:
    status_filter = [s.strip() for s in status.split(",")] if status else None
    severity_filter = [s.strip() for s in severity.split(",")] if severity else None
    return await get_anomaly_feed(
        db,
        status_filter=status_filter,
        severity_filter=severity_filter,
        entity_type=entity_type,
        entity_id=entity_id,
        follow_up=follow_up,
        limit=limit,
    )


@router.patch("/{anomaly_id}", response_model=AnomalyItem)
async def patch_anomaly(
    anomaly_id: uuid.UUID,
    body: AnomalyStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> AnomalyItem:
    if body.status == "dismissed" and not body.reason:
        raise HTTPException(status_code=422, detail="Dismiss requires a reason")
    item = await update_anomaly_status(
        db,
        anomaly_id,
        body.status,
        operator_name=body.operator_name,
        reason=body.reason,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    await db.commit()
    return item
