"""Anomaly feed sub-agent."""

from __future__ import annotations

import uuid

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import SEVERITY_RANK
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


def _severity_order():
    return case(
        (Anomaly.severity == "critical", SEVERITY_RANK["critical"]),
        (Anomaly.severity == "warning", SEVERITY_RANK["warning"]),
        (Anomaly.severity == "info", SEVERITY_RANK["info"]),
        else_=3,
    )


async def get_anomaly_feed(
    db: AsyncSession,
    status_filter: list[str] | None = None,
    severity_filter: list[str] | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    follow_up: bool | None = None,
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
    if follow_up is True:
        query = query.where(Anomaly.supporting_data["follow_up"].as_boolean() == True)  # noqa: E712
    elif follow_up is False:
        query = query.where(
            (Anomaly.supporting_data["follow_up"].as_boolean() == False)  # noqa: E712
            | (Anomaly.supporting_data["follow_up"].is_(None))
        )

    query = query.order_by(_severity_order(), Anomaly.detected_at.desc()).limit(limit)

    rows = (await db.execute(query)).scalars().all()
    items: list[AnomalyItem] = []
    for row in rows:
        name = await _resolve_entity_name(db, row.entity_type, row.entity_id)
        sd = row.supporting_data if isinstance(row.supporting_data, dict) else {}
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
                follow_up=bool(sd.get("follow_up")),
                conversation_id=uuid.UUID(str(sd["conversation_id"])) if sd.get("conversation_id") else None,
            )
        )

    from sqlalchemy import func

    counts_base = select(func.count()).select_from(Anomaly).where(Anomaly.tenant_id == tenant_id)
    total = (await db.execute(counts_base)).scalar_one() or 0
    new_c = (await db.execute(counts_base.where(Anomaly.status == "new"))).scalar_one() or 0
    ack = (await db.execute(counts_base.where(Anomaly.status == "acknowledged"))).scalar_one() or 0
    inv = (await db.execute(counts_base.where(Anomaly.status == "investigating"))).scalar_one() or 0

    return AnomalyFeedResponse(
        anomalies=items,
        counts=AnomalyCounts(total=total, new=new_c, acknowledged=ack, investigating=inv),
    )
