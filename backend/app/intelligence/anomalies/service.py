"""Anomaly upsert, dedup, and lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import ACTIVE_ANOMALY_STATUSES, TERMINAL_ANOMALY_STATUSES, THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.anomaly import Anomaly
from app.models.conversation import Conversation


def _dedup_key(candidate: AnomalyCandidate) -> str:
    if candidate.dedup_key:
        return candidate.dedup_key
    metric = candidate.supporting_data.get("metric") or candidate.supporting_data.get("compliance_type")
    entity = str(candidate.entity_id) if candidate.entity_id else "fleet"
    return f"{candidate.anomaly_type}:{candidate.entity_type}:{entity}:{metric}"


async def _has_active_duplicate(
    db: AsyncSession,
    candidate: AnomalyCandidate,
    tenant_id: int,
) -> bool:
    key = _dedup_key(candidate)
    query = select(Anomaly).where(
        Anomaly.tenant_id == tenant_id,
        Anomaly.anomaly_type == candidate.anomaly_type,
        Anomaly.entity_type == candidate.entity_type,
        Anomaly.status.in_(list(ACTIVE_ANOMALY_STATUSES)),
    )
    if candidate.entity_id:
        query = query.where(Anomaly.entity_id == candidate.entity_id)
    else:
        query = query.where(Anomaly.entity_id.is_(None))
    rows = (await db.execute(query)).scalars().all()
    for row in rows:
        row_key = f"{row.anomaly_type}:{row.entity_type}:{row.entity_id or 'fleet'}:"
        sd = row.supporting_data if isinstance(row.supporting_data, dict) else {}
        row_key += str(sd.get("metric") or sd.get("compliance_type") or "")
        if row_key == key:
            return True
    return False


async def _in_recent_conversation_findings(
    db: AsyncSession,
    candidate: AnomalyCandidate,
    tenant_id: int,
) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=THRESHOLDS.conversation_dedup_days)
    stmt = select(Conversation).where(
        Conversation.tenant_id == tenant_id,
        Conversation.ended_at.isnot(None),
        Conversation.ended_at >= cutoff,
        Conversation.key_findings.isnot(None),
    )
    entity_str = str(candidate.entity_id) if candidate.entity_id else None
    for conv in (await db.execute(stmt)).scalars().all():
        findings = conv.key_findings
        if not isinstance(findings, list):
            continue
        for item in findings:
            if not isinstance(item, dict):
                continue
            if item.get("anomaly_type") == candidate.anomaly_type:
                if entity_str and str(item.get("entity_id", "")) == entity_str:
                    return True
                if not entity_str and not item.get("entity_id"):
                    return True
    return False


async def upsert_anomaly(
    db: AsyncSession,
    candidate: AnomalyCandidate,
    *,
    tenant_id: int = 1,
) -> tuple[Anomaly | None, bool]:
    """Create anomaly if not duplicate. Returns (row, created)."""
    if await _has_active_duplicate(db, candidate, tenant_id):
        return None, False
    if await _in_recent_conversation_findings(db, candidate, tenant_id):
        return None, False

    row = Anomaly(
        tenant_id=tenant_id,
        anomaly_type=candidate.anomaly_type,
        entity_type=candidate.entity_type,
        entity_id=candidate.entity_id,
        description=candidate.description,
        severity=candidate.severity,
        supporting_data=candidate.supporting_data,
        status="new",
    )
    db.add(row)
    await db.flush()
    return row, True


async def update_anomaly_status(
    db: AsyncSession,
    anomaly_id: uuid.UUID,
    status: str,
    *,
    operator_name: str | None = None,
    reason: str | None = None,
    tenant_id: int = 1,
) -> Anomaly | None:
    row = (
        await db.execute(
            select(Anomaly).where(Anomaly.id == anomaly_id, Anomaly.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = status
    if status == "dismissed" and reason:
        row.operator_feedback = {
            "reason": reason,
            "operator_name": operator_name,
            "dismissed_at": datetime.now(timezone.utc).isoformat(),
        }
    if status == "investigating" and operator_name:
        from app.chat.session import append_investigating_unresolved_item

        await append_investigating_unresolved_item(
            db,
            operator_name,
            anomaly_id=row.id,
            description=row.description,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            tenant_id=tenant_id,
        )
    if status in TERMINAL_ANOMALY_STATUSES:
        row.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return row


async def auto_resolve_matching(
    db: AsyncSession,
    *,
    anomaly_type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    note: str,
    compliance_type: str | None = None,
    tenant_id: int = 1,
) -> int:
    query = select(Anomaly).where(
        Anomaly.tenant_id == tenant_id,
        Anomaly.anomaly_type == anomaly_type,
        Anomaly.entity_type == entity_type,
        Anomaly.status.in_(list(ACTIVE_ANOMALY_STATUSES)),
    )
    if entity_id:
        query = query.where(Anomaly.entity_id == entity_id)
    else:
        query = query.where(Anomaly.entity_id.is_(None))

    resolved = 0
    now = datetime.now(timezone.utc)
    for row in (await db.execute(query)).scalars().all():
        if compliance_type:
            sd = row.supporting_data if isinstance(row.supporting_data, dict) else {}
            if sd.get("compliance_type") != compliance_type:
                continue
        row.status = "resolved"
        row.resolved_at = now
        row.operator_feedback = {"auto_resolve_note": note, "resolved_at": now.isoformat()}
        resolved += 1
    if resolved:
        await db.flush()
    return resolved


async def resolve_cost_spikes_for_truck(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> int:
    from app.intelligence.metrics_store import get_fleet_metric

    mean_row = await get_fleet_metric(
        db,
        entity_type="truck",
        entity_id=truck_id,
        metric_name="maintenance_monthly_spend_mean",
        period_type="monthly",
        tenant_id=tenant_id,
    )
    sd_row = await get_fleet_metric(
        db,
        entity_type="truck",
        entity_id=truck_id,
        metric_name="maintenance_monthly_spend_sd",
        period_type="monthly",
        tenant_id=tenant_id,
    )
    latest_row = await get_fleet_metric(
        db,
        entity_type="truck",
        entity_id=truck_id,
        metric_name="maintenance_monthly_spend_latest",
        period_type="monthly",
        tenant_id=tenant_id,
    )
    if not mean_row or not sd_row or not latest_row:
        return 0
    threshold = float(mean_row.metric_value) + THRESHOLDS.cost_spike_auto_resolve_sd * float(
        sd_row.metric_value
    )
    if float(latest_row.metric_value) > threshold:
        return 0
    return await auto_resolve_matching(
        db,
        anomaly_type="cost_spike",
        entity_type="truck",
        entity_id=truck_id,
        note="Resolved: maintenance spend returned to normal levels.",
        tenant_id=tenant_id,
    )
