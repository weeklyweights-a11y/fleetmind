"""IRS Form 2290 (Highway Use Tax) extractor."""

from __future__ import annotations

import re

from app.enums import DocumentType
from app.extraction.text_utils import extract_vin, fields_from_labels
from app.extraction.types import ExtractionResult, LayoutResult

FIELDS = {
    "vin": {"labels": ["VIN", "Vehicle Identification Number"], "pattern": r"([A-HJ-NPR-Z0-9]{17})"},
    "tax_year": {"labels": ["Tax Year"], "pattern": r"(20\d{2})"},
    "taxable_gross_weight": {"labels": ["Taxable Gross Weight"], "pattern": r"([\d,]+)"},
}


def extract(layout: LayoutResult) -> ExtractionResult:
    fields, confidences = fields_from_labels(layout.full_text, FIELDS)
    if "vin" not in fields:
        vin = extract_vin(layout.full_text)
        if vin:
            fields["vin"] = vin
            confidences["vin"] = 0.85
    return ExtractionResult(
        document_type=DocumentType.FORM_2290.value,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
