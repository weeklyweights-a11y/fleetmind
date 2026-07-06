"""Persist fleet_metrics baseline rows."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fleet_metrics import FleetMetric


async def upsert_fleet_metric(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
    metric_name: str,
    value: Decimal | float,
    period_type: str,
    period_start: date,
    period_end: date,
    tenant_id: int = 1,
) -> FleetMetric:
    """Insert or update a single fleet_metrics row for the given period."""
    numeric = Decimal(str(value))
    now = datetime.now(timezone.utc)
    stmt = insert(FleetMetric).values(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metric_name=metric_name,
        metric_value=numeric,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        computed_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            "tenant_id",
            "entity_type",
            "entity_id",
            "metric_name",
            "period_type",
            "period_start",
        ],
        set_={
            "metric_value": numeric,
            "period_end": period_end,
            "computed_at": now,
            "updated_at": now,
        },
    ).returning(FleetMetric)
    row = (await db.execute(stmt)).scalar_one()
    return row


async def get_fleet_metric(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
    metric_name: str,
    period_type: str,
    period_start: date | None = None,
    tenant_id: int = 1,
) -> FleetMetric | None:
    query = select(FleetMetric).where(
        FleetMetric.tenant_id == tenant_id,
        FleetMetric.entity_type == entity_type,
        FleetMetric.entity_id == entity_id,
        FleetMetric.metric_name == metric_name,
        FleetMetric.period_type == period_type,
    )
    if period_start is not None:
        query = query.where(FleetMetric.period_start == period_start)
    query = query.order_by(FleetMetric.period_start.desc()).limit(1)
    return (await db.execute(query)).scalar_one_or_none()
