"""Loop 2 — entity resolution stats."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def compute_entity_resolution_stats(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    total = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status.in_(["complete", "needs_review"]),
            )
        )
    ).scalar_one() or 0
    auto = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "complete",
                Document.entity_resolution_confidence >= 0.9,
            )
        )
    ).scalar_one() or 0
    review = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "needs_review",
            )
        )
    ).scalar_one() or 0
    failures = (
        await db.execute(
            select(Document.id, Document.document_type, Document.entity_resolution_confidence)
            .where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "needs_review",
                or_(
                    Document.entity_resolution_confidence < 0.9,
                    Document.entity_resolution_confidence.is_(None),
                    Document.truck_id.is_(None),
                ),
            )
            .limit(20)
        )
    ).all()
    return {
        "auto_resolution_rate_pct": round(auto / total * 100, 2) if total else 0.0,
        "human_review_rate_pct": round(review / total * 100, 2) if total else 0.0,
        "common_failures": [
            {"document_id": str(r[0]), "document_type": r[1], "confidence": float(r[2]) if r[2] else None}
            for r in failures
        ],
    }
