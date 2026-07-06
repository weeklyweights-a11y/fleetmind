"""Anomaly lifecycle actions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.anomalies.service import update_anomaly_status as _update_status
from app.models.anomaly import Anomaly
from app.schemas.anomalies import AnomalyItem


async def update_anomaly_status(
    db: AsyncSession,
    anomaly_id: uuid.UUID,
    status: str,
    *,
    operator_name: str | None = None,
    reason: str | None = None,
    tenant_id: int = 1,
) -> AnomalyItem | None:
    row = await _update_status(
        db, anomaly_id, status, operator_name=operator_name, reason=reason, tenant_id=tenant_id
    )
    if row is None:
        return None
    from app.agents.anomaly_feed import _resolve_entity_name

    name = await _resolve_entity_name(db, row.entity_type, row.entity_id)
    sd = row.supporting_data if isinstance(row.supporting_data, dict) else {}
    return AnomalyItem(
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
