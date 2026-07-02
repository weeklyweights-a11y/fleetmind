"""Anomaly feed sub-agent (Phase 6 data stub)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly import Anomaly
from app.models.driver import Driver
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.schemas.anomalies import AnomalyCounts, AnomalyFeedResponse, AnomalyItem


DEFAULT_STATUSES = ["new", "acknowledged", "investigating"]


async def _resolve_entity_name(
    db: AsyncSession, entity_type: str, entity_id: uuid.UUID | None
) -> str | None:
    if entity_id is None:
        return None
    if entity_type == "truck":
        unit = (await db.execute(select(Truck.unit_number).where(Truck.id == entity_id))).scalar_one_or_none()
        return f"Unit {unit}" if unit is not None else None
    if entity_type == "driver":
        return (await db.execute(select(Driver.full_name).where(Driver.id == entity_id))).scalar_one_or_none()
    if entity_type == "vendor":
        return (await db.execute(select(Vendor.name).where(Vendor.id == entity_id))).scalar_one_or_none()
    return None


async def get_anomaly_feed(
    db: AsyncSession,
    status_filter: list[str] | None = None,
    severity_filter: list[str] | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = 20,
    tenant_id: int = 1,
) -> AnomalyFeedResponse:
    statuses = status_filter or DEFAULT_STATUSES
    query = select(Anomaly).where(Anomaly.tenant_id == tenant_id, Anomaly.status.in_(statuses))
    if severity_filter:
        query = query.where(Anomaly.severity.in_(severity_filter))
    if entity_type:
        query = query.where(Anomaly.entity_type == entity_type)
    if entity_id:
        query = query.where(Anomaly.entity_id == entity_id)
    query = query.order_by(Anomaly.detected_at.desc()).limit(limit)

    rows = (await db.execute(query)).scalars().all()
    items: list[AnomalyItem] = []
    for row in rows:
        name = await _resolve_entity_name(db, row.entity_type, row.entity_id)
        items.append(
            AnomalyItem(
                anomaly_id=row.id,
                type=row.anomaly_type,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                entity_name=name,
                description=row.description,
                severity=row.severity,
                supporting_data=row.supporting_data,
                status=row.status,
                detected_at=row.detected_at,
            )
        )

    counts_base = select(func.count()).select_from(Anomaly).where(Anomaly.tenant_id == tenant_id)
    total = (await db.execute(counts_base)).scalar_one() or 0
    new_c = (await db.execute(counts_base.where(Anomaly.status == "new"))).scalar_one() or 0
    ack = (await db.execute(counts_base.where(Anomaly.status == "acknowledged"))).scalar_one() or 0
    inv = (await db.execute(counts_base.where(Anomaly.status == "investigating"))).scalar_one() or 0

    return AnomalyFeedResponse(
        anomalies=items,
        counts=AnomalyCounts(total=total, new=new_c, acknowledged=ack, investigating=inv),
    )
