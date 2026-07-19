"""IFTA filing extractor."""

from __future__ import annotations

import re

from app.enums import DocumentType
from app.extraction import schemas
from app.extraction.text_utils import collapse_spaced_text, fields_from_labels, parse_int_from_text
from app.extraction.types import ExtractionResult, LayoutResult


def _parse_vehicle_details(text: str) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for vin in re.findall(r"\b([A-HJ-NPR-Z0-9]{17})\b", text):
        window = text[text.find(vin) : text.find(vin) + 120]
        nums = re.findall(r"([\d,]+)", window)
        miles = parse_int_from_text(nums[1]) if len(nums) > 1 else None
        gallons = parse_int_from_text(nums[2]) if len(nums) > 2 else None
        if miles or gallons:
            details.append({"vin": vin, "miles": miles or "", "gallons": gallons or ""})
    return details


def _parse_jurisdiction_details(text: str) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for m in re.finditer(
        r"\b([A-Z]{2})\b\s+([\d,]+)\s+([\d,.]+)\s+([\d,.]+)\s+([\d.]+)\s+([\d,.]+)",
        text,
    ):
        details.append(
            {
                "jurisdiction": m.group(1),
                "miles": m.group(2),
                "gallons": m.group(3),
                "taxable_gallons": m.group(4),
                "tax_rate": m.group(5),
                "tax_due": m.group(6),
            }
        )
    return details


def extract(layout: LayoutResult) -> ExtractionResult:
    text = collapse_spaced_text(layout.full_text)
    fields, confidences = fields_from_labels(text, schemas.ifta_filing.FIELDS)

    if "quarter" not in fields:
        m = re.search(r"(20\d{2})\s*Q([1-4])", text, re.I)
        if m:
            fields["quarter"] = f"{m.group(1)}Q{m.group(2)}"
            confidences["quarter"] = 0.9

    mpg_raw = fields.get("average_fleet_mpg", "")
    if mpg_raw and not re.search(r"^\s*[\d.]", str(mpg_raw)):
        fields.pop("average_fleet_mpg", None)

    miles = parse_int_from_text(str(fields.get("total_miles", "")))
    gallons = parse_int_from_text(str(fields.get("total_gallons", "")))
    if miles and gallons and gallons > 0 and "average_fleet_mpg" not in fields:
        fields["average_fleet_mpg"] = f"{miles / gallons:.2f}"
        confidences["average_fleet_mpg"] = 0.85

    vehicle_details = _parse_vehicle_details(text)
    if vehicle_details:
        fields["vehicle_details"] = vehicle_details
        confidences["vehicle_details"] = 0.8

    jurisdiction_details = _parse_jurisdiction_details(text)
    if jurisdiction_details:
        fields["jurisdiction_details"] = jurisdiction_details
        confidences["jurisdiction_details"] = 0.8

    return ExtractionResult(
        document_type=DocumentType.IFTA_FILING.value,
        extracted_fields=fields,
        extraction_method="rule_based",
        field_confidences=confidences,
    )
