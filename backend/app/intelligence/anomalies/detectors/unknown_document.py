"""Unknown document type cluster detection."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.config import THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.document import Document


async def detect_unknown_document(
    db: AsyncSession,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    cutoff = date.today() - timedelta(days=THRESHOLDS.unknown_document_days)
    count = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.document_type == "unknown",
                Document.created_at >= cutoff,
            )
        )
    ).scalar_one() or 0
    if count < THRESHOLDS.unknown_document_count:
        return []

    return [
        AnomalyCandidate(
            anomaly_type="unknown_document",
            entity_type="fleet",
            entity_id=None,
            description=f"{count} unclassified documents in the last {THRESHOLDS.unknown_document_days} days.",
            severity="warning",
            supporting_data={"metric": "unknown_document_count", "current_value": count},
            dedup_key="unknown_document:fleet:unknown_document_count",
        )
    ]
