"""Human document review — writes ExtractionCorrection and updates normalized rows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ProcessingStatus
from app.models.document import Document
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.driver import Driver
from app.models.extraction_correction import ExtractionCorrection
from app.models.insurance_coverage import InsuranceCoverage
from app.models.maintenance_event import MaintenanceEvent
from app.models.registration import Registration
from app.models.title import Title
from app.models.truck import Truck
from app.schemas.documents import DocumentCorrectionItem, DocumentReviewSubmitResponse
from app.services.queue import enqueue_document_job
from app.services.truck_unit_lookup import resolve_truck_unit
from app.websocket.events import notify_document_event

TABLE_MODEL_MAP: dict[str, Any] = {
    "trucks": Truck,
    "drivers": Driver,
    "insurance_coverages": InsuranceCoverage,
    "maintenance_events": MaintenanceEvent,
    "registrations": Registration,
    "titles": Title,
}


async def _emit_review_notify(db: AsyncSession, doc: Document) -> None:
    truck_unit = await resolve_truck_unit(db, doc.truck_id)
    payload: dict[str, Any] = {
        "document_id": str(doc.id),
        "status": doc.processing_status,
        "filename": doc.original_filename,
        "document_type": doc.document_type,
        "event_type": "review",
    }
    if truck_unit is not None:
        payload["truck_unit"] = truck_unit
    if doc.truck_id:
        payload["truck_id"] = str(doc.truck_id)
    await notify_document_event(payload)


async def apply_document_review(
    db: AsyncSession,
    document_id: uuid.UUID,
    action: str,
    corrections: list[DocumentCorrectionItem],
    corrected_by: str | None,
    reprocess: bool,
    reject_reason: str | None = None,
) -> DocumentReviewSubmitResponse:
    doc = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if doc is None:
        from app.exceptions import DocumentNotFoundError

        raise DocumentNotFoundError(str(document_id))

    applied = 0
    requeued = False

    if action == "approve":
        doc.processing_status = ProcessingStatus.COMPLETE.value
        doc.review_status = "approved"
    elif action == "reject":
        doc.processing_status = ProcessingStatus.FAILED.value
        doc.review_status = "rejected"
        doc.error_details = reject_reason or "Rejected by reviewer"
    else:
        norm_rows = (
            await db.execute(
                select(DocumentNormalizedRecord).where(DocumentNormalizedRecord.document_id == document_id)
            )
        ).scalars().all()

        for correction in corrections:
            db.add(
                ExtractionCorrection(
                    document_id=document_id,
                    field_name=correction.field_name,
                    original_value=None,
                    corrected_value=correction.corrected_value,
                    correction_source="human_review",
                    corrected_by=corrected_by,
                    tenant_id=doc.tenant_id,
                )
            )
            for norm in norm_rows:
                model_cls = TABLE_MODEL_MAP.get(norm.target_table)
                if model_cls is None:
                    continue
                record = (
                    await db.execute(select(model_cls).where(model_cls.id == norm.target_record_id))
                ).scalar_one_or_none()
                if record is None:
                    continue
                if hasattr(record, correction.field_name):
                    setattr(record, correction.field_name, correction.corrected_value)
                    applied += 1
                    break

        doc.review_status = "corrected"
        doc.processing_status = ProcessingStatus.COMPLETE.value
        if reprocess:
            doc.processing_status = ProcessingStatus.QUEUED.value
            requeued = True
            await enqueue_document_job(
                document_id=doc.id,
                file_path=doc.file_path,
                original_filename=doc.original_filename,
                tenant_id=doc.tenant_id,
            )

    await db.flush()
    await _emit_review_notify(db, doc)
    await db.commit()

    return DocumentReviewSubmitResponse(
        document_id=document_id,
        review_status=doc.review_status or action,
        corrections_applied=applied or len(corrections),
        requeued=requeued,
    )
