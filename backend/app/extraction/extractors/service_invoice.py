"""Service invoice extractor."""

from __future__ import annotations

import re

from app.enums import DocumentType
from app.extraction import schemas
from app.extraction.text_utils import collapse_spaced_text, extract_vin, fields_from_labels
from app.extraction.types import ExtractionResult, LayoutResult


def extract(layout: LayoutResult) -> ExtractionResult:
    text = collapse_spaced_text(layout.full_text)
    fields, confidences = fields_from_labels(text, schemas.service_invoice.FIELDS)

    lines = [ln.strip() for ln in layout.full_text.splitlines() if ln.strip()]
    if lines and "vendor_name" not in fields:
        fields["vendor_name"] = collapse_spaced_text(lines[0])
        confidences["vendor_name"] = 0.9

    if "PAID" in text.upper() and "payment_status" not in fields:
        fields["payment_status"] = "PAID"
        confidences["payment_status"] = 0.95

    if "vin" not in fields:
        vin = extract_vin(text)
        if vin:
            fields["vin"] = vin
            confidences["vin"] = 0.9

    if "invoice_number" not in fields:
        m = re.search(r"([A-Z]{2,3}-\d+)", text)
        if m:
            fields["invoice_number"] = m.group(1)
            confidences["invoice_number"] = 0.85

    return ExtractionResult(
        document_type=DocumentType.SERVICE_INVOICE.value,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
