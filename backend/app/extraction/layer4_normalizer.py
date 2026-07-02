"""Layer 4: Normalization."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as date_parser

from app.extraction.text_utils import collapse_spaced_text
from app.extraction.types import NormalizationIssue


def _parse_date(value: str) -> date | None:
    try:
        return date_parser.parse(value, dayfirst=False).date()
    except (ValueError, TypeError):
        return None


def _parse_decimal(value: str) -> Decimal | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: str) -> int | None:
    if value is None:
        return None
    m = re.search(r"-?[\d,]+", str(value).replace(" ", ""))
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


def normalize_fields(
    fields: dict[str, Any],
) -> tuple[dict[str, Any], list[NormalizationIssue]]:
    normalized: dict[str, Any] = {}
    issues: list[NormalizationIssue] = []

    date_fields = {
        "document_date",
        "date_of_birth",
        "license_issue_date",
        "license_expiry_date",
        "effective_date",
        "expiry_date",
        "invoice_date",
        "issue_date",
        "filing_date",
        "notary_commission_expiry",
    }
    money_fields = {
        "purchase_price",
        "sale_price",
        "subtotal",
        "labor_cost",
        "sales_tax",
        "total",
        "registration_fee",
        "property_tax",
        "irp_apportioned_fee",
        "title_fee",
        "total_fees",
        "total_tax_due",
        "balance_due",
        "liability_limit",
        "cargo_limit",
        "title_fee",
    }
    int_fields = {
        "year",
        "unit_number",
        "fleet_unit_no",
        "odometer",
        "weight",
        "registered_weight",
        "gross_weight",
        "total_miles",
        "total_gallons",
        "fleet_unit_assignment",
    }
    decimal_fields = {"average_fleet_mpg"}

    for key, raw in fields.items():
        if raw is None:
            continue
        value = collapse_spaced_text(str(raw)).strip()

        if key == "vin":
            value = re.sub(r"[\s\-]", "", value.upper())
            if len(value) != 17:
                issues.append(NormalizationIssue(key, str(raw), "VIN length not 17"))
            normalized[key] = value
        elif key in date_fields:
            parsed = _parse_date(value)
            if parsed is None:
                issues.append(NormalizationIssue(key, str(raw), "Could not parse date"))
            else:
                normalized[key] = parsed
        elif key in money_fields:
            parsed = _parse_decimal(value)
            if parsed is None:
                issues.append(NormalizationIssue(key, str(raw), "Could not parse money"))
            else:
                normalized[key] = parsed
        elif key in decimal_fields:
            parsed = _parse_decimal(value)
            if parsed is None and key == "average_fleet_mpg":
                m = re.search(r"([\d.]+)\s*(?:MPG|mpg)", value, re.I)
                if m:
                    parsed = Decimal(m.group(1)).quantize(Decimal("0.01"))
            if parsed is None:
                issues.append(NormalizationIssue(key, str(raw), "Could not parse decimal"))
            else:
                normalized[key] = parsed
        elif key in int_fields:
            if key == "fleet_unit_assignment" and value.lower() == "none":
                normalized[key] = None
            else:
                parsed = _parse_int(value)
                if parsed is None:
                    issues.append(NormalizationIssue(key, str(raw), "Could not parse integer"))
                else:
                    normalized[key] = parsed
        elif key == "license_number":
            normalized[key] = value.upper().replace(" ", "")
        elif key == "endorsements":
            normalized[key] = value.upper()
        elif key == "quarter":
            normalized[key] = re.sub(r"\s+", "", value.upper())
        elif key in ("vehicle_details", "jurisdiction_details"):
            normalized[key] = raw
        else:
            normalized[key] = value

    return normalized, issues
