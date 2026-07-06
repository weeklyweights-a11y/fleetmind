"""Loop 1 — extraction accuracy."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.extraction_correction import ExtractionCorrection


async def compute_extraction_accuracy(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    total = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.tenant_id == tenant_id, Document.processing_status == "complete",
            )
        )
    ).scalar_one() or 0
    corrected_docs = (
        await db.execute(
            select(func.count(func.distinct(ExtractionCorrection.document_id))).where(
                ExtractionCorrection.tenant_id == tenant_id,
            )
        )
    ).scalar_one() or 0
    accuracy = (total - corrected_docs) / total * 100 if total else 0.0
    by_type_rows = (
        await db.execute(
            select(Document.document_type, func.count())
            .where(Document.tenant_id == tenant_id, Document.processing_status == "complete")
            .group_by(Document.document_type)
        )
    ).all()
    return {
        "overall_accuracy_pct": round(accuracy, 2),
        "total_processed": total,
        "documents_with_corrections": corrected_docs,
        "by_document_type": {str(r[0]): r[1] for r in by_type_rows},
    }
