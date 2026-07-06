"""Load proactive alerts for chat context."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.anomaly_feed import get_anomaly_feed


async def load_proactive_alerts(db: AsyncSession, *, tenant_id: int = 1, limit: int = 5) -> list[dict]:
    feed = await get_anomaly_feed(
        db,
        severity_filter=["critical", "warning"],
        limit=limit,
        tenant_id=tenant_id,
    )
    alerts = []
    for item in feed.anomalies:
        alerts.append(
            {
                "type": "anomaly",
                "severity": item.severity,
                "description": item.description,
                "anomaly_id": str(item.anomaly_id),
                "entity_type": item.entity_type,
                "entity_id": str(item.entity_id) if item.entity_id else None,
            }
        )
    return alerts
