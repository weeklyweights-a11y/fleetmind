"""CDL extractor."""

from __future__ import annotations

import re

from app.enums import DocumentType
from app.extraction import schemas
from app.extraction.text_utils import collapse_spaced_text, fields_from_labels
from app.extraction.types import ExtractionResult, LayoutResult


def extract(layout: LayoutResult) -> ExtractionResult:
    text = collapse_spaced_text(layout.full_text)
    fields, confidences = fields_from_labels(text, schemas.cdl.FIELDS)

    header = re.search(
        r"SCANNED DOCUMENT\s*[—-]\s*CDL-(D\d+)\s*[—-]\s*(D\d+)\s*/\s*FLEET\s*(\d+|None)",
        text,
        re.I,
    )
    if header:
        fields["driver_code"] = header.group(2)
        fields["fleet_unit_assignment"] = header.group(3)
        confidences["driver_code"] = 1.0
        confidences["fleet_unit_assignment"] = 1.0

    if "full_name" not in fields:
        m = re.search(r"CLASS\s+([A-Za-z]+\s+[A-Za-z]+)", text)
        if m:
            fields["full_name"] = m.group(1).strip()
            confidences["full_name"] = 0.85

    return ExtractionResult(
        document_type=DocumentType.CDL.value,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
