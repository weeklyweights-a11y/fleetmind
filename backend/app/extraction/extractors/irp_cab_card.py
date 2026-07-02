"""IRP cab card extractor."""

from __future__ import annotations

from app.enums import DocumentType
from app.extraction import schemas
from app.extraction.text_utils import extract_vin, fields_from_labels
from app.extraction.types import ExtractionResult, LayoutResult


def extract(layout: LayoutResult) -> ExtractionResult:
    fields, confidences = fields_from_labels(layout.full_text, schemas.irp_cab_card.FIELDS)
    if "vin" not in fields:
        vin = extract_vin(layout.full_text)
        if vin:
            fields["vin"] = vin
            confidences["vin"] = 0.9
    return ExtractionResult(
        document_type=DocumentType.IRP_CAB_CARD.value,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
