"""Build document extraction payload for viewer and review UI."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DocumentNotFoundError
from app.models.document import Document
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.extraction_correction import ExtractionCorrection
from app.schemas.documents import DocumentExtractionField, DocumentExtractionResponse


def _build_description_from_notes(notes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float], list[dict]]:
    extracted = notes.get("extracted_fields") or {}
    confidences = notes.get("field_confidences") or {}
    failures = []
    for field in notes.get("fields_needing_attention") or []:
        failures.append({"field": field, "message": "Validation failed"})
    for vr in notes.get("validation_results") or []:
        if vr.get("field"):
            failures.append(
                {
                    "field": vr["field"],
                    "message": f"{vr.get('check_type', 'validation')}: expected {vr.get('expected')}, got {vr.get('actual')}",
                }
            )
    return extracted, confidences, failures


async def get_document_extraction(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> DocumentExtractionResponse:
    doc = (
        await db.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundError(str(document_id))

    corrections = (
        await db.execute(
            select(ExtractionCorrection).where(ExtractionCorrection.document_id == document_id)
        )
    ).scalars().all()
    correction_map = {c.field_name: c for c in corrections}

    extracted: dict[str, Any] = {}
    confidences: dict[str, float] = {}
    validation_failures: list[dict[str, str]] = []

    if doc.review_notes:
        try:
            notes = json.loads(doc.review_notes)
            extracted, confidences, validation_failures = _build_description_from_notes(notes)
        except json.JSONDecodeError:
            pass

    if not extracted:
        norm_rows = (
            await db.execute(
                select(DocumentNormalizedRecord).where(
                    DocumentNormalizedRecord.document_id == document_id
                )
            )
        ).scalars().all()
        for norm in norm_rows:
            extracted[f"{norm.target_table}_record"] = str(norm.target_record_id)

    fields: list[DocumentExtractionField] = []
    for name, value in extracted.items():
        corr = correction_map.get(name)
        fail_msg = next((f["message"] for f in validation_failures if f["field"] == name), None)
        fields.append(
            DocumentExtractionField(
                name=name,
                value=value,
                confidence=float(confidences.get(name)) if confidences.get(name) is not None else None,
                corrected=corr is not None,
                correction_source=corr.correction_source if corr else None,
                validation_error=fail_msg,
            )
        )

    return DocumentExtractionResponse(
        document_id=document_id,
        document_type=doc.document_type,
        fields=fields,
        validation_failures=validation_failures,
    )
