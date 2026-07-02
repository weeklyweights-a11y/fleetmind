"""Bill of Sale extractor."""

from __future__ import annotations

import re

from app.extraction import schemas
from app.extraction.layer5_validator import YEAR_CHAR
from app.extraction.text_utils import collapse_spaced_text, extract_vin, fields_from_labels, parse_int_from_text
from app.extraction.types import ExtractionResult, LayoutResult


def extract(layout: LayoutResult, document_type: str) -> ExtractionResult:
    text = layout.full_text
    fields, confidences = fields_from_labels(text, schemas.bill_of_sale.FIELDS)

    m = re.search(r"(BOS-[A-Z0-9-]+)", collapse_spaced_text(text), re.I)
    if m:
        fields.setdefault("document_number", m.group(1))
        confidences["document_number"] = 1.0
        um = re.search(r"-(\d+)$", m.group(1))
        if um and "fleet_unit_no" not in fields:
            fields["fleet_unit_no"] = um.group(1).lstrip("0") or "0"
            confidences["fleet_unit_no"] = 0.8

    if "vin" not in fields:
        vin = extract_vin(text)
        if vin:
            fields["vin"] = vin
            confidences["vin"] = 0.9

    if "year" not in fields and fields.get("vin") and len(str(fields["vin"])) >= 10:
        yc = str(fields["vin"])[9]
        if yc in YEAR_CHAR:
            fields["year"] = str(YEAR_CHAR[yc])
            confidences["year"] = 0.75

    if "fleet_unit_no" in fields:
        fields["fleet_unit_no"] = parse_int_from_text(str(fields["fleet_unit_no"])) or fields["fleet_unit_no"]

    return ExtractionResult(
        document_type=document_type,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
