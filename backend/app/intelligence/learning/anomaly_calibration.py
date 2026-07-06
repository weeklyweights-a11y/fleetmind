"""Loop 4 — anomaly calibration."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anomaly import Anomaly


async def compute_anomaly_calibration(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    total = (
        await db.execute(select(func.count()).select_from(Anomaly).where(Anomaly.tenant_id == tenant_id))
    ).scalar_one() or 0
    acted = (
        await db.execute(
            select(func.count()).select_from(Anomaly).where(
                Anomaly.tenant_id == tenant_id,
                Anomaly.status.in_(["acknowledged", "investigating", "resolved"]),
            )
        )
    ).scalar_one() or 0
    dismissed = (
        await db.execute(
            select(func.count()).select_from(Anomaly).where(
                Anomaly.tenant_id == tenant_id, Anomaly.status == "dismissed",
            )
        )
    ).scalar_one() or 0
    precision = acted / total * 100 if total else 0.0
    dismiss_rate = dismissed / total * 100 if total else 0.0
    return {
        "total_anomalies": total,
        "precision_pct": round(precision, 2),
        "dismiss_rate_pct": round(dismiss_rate, 2),
    }
