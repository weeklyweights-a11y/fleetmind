"""Layer 5: Validation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.extraction.types import FieldValidationResult, ValidationResult

VIN_TRANSLITERATION = {
    **{str(i): i for i in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
WMI_MAKE = {
    "3AK": "Freightliner",
    "3AL": "Freightliner",
    "4V4": "Volvo",
    "1XP": "Peterbilt",
    "1XK": "Peterbilt",
    "3HS": "International",
}
YEAR_CHAR = {
    "A": 2010,
    "B": 2011,
    "C": 2012,
    "D": 2013,
    "E": 2014,
    "F": 2015,
    "G": 2016,
    "H": 2017,
    "J": 2018,
    "K": 2019,
    "L": 2020,
    "M": 2021,
    "N": 2022,
    "P": 2023,
    "R": 2024,
    "S": 2025,
    "T": 2026,
}

# Soft checks are logged but do not block completion.
SOFT_CHECKS = {"wmi_make", "vin_year", "invoice_sum"}


def vin_check_digit_valid(vin: str) -> bool:
    if len(vin) != 17:
        return False
    total = 0
    for i, ch in enumerate(vin):
        val = VIN_TRANSLITERATION.get(ch)
        if val is None:
            return False
        total += val * VIN_WEIGHTS[i]
    remainder = total % 11
    check = "X" if remainder == 10 else str(remainder)
    return vin[8] == check


def _make_matches_wmi(make: str, wmi: str) -> bool:
    expected = WMI_MAKE.get(wmi, "").lower()
    if not expected or not make:
        return True
    make_l = make.lower()
    return expected in make_l or make_l in expected


def validate_fields(
    document_type: str,
    fields: dict[str, Any],
    field_confidences: dict[str, float],
    l1_confidence: float,
) -> ValidationResult:
    field_results: dict[str, FieldValidationResult] = {}
    failed: list[str] = []
    warnings: list[str] = []

    def add(
        field: str,
        valid: bool,
        check: str,
        expected: str,
        actual: str,
        impact: float = 0.2,
        *,
        hard: bool = True,
    ):
        field_results[field] = FieldValidationResult(valid, check, expected, actual, impact)
        if valid:
            return
        if hard and check not in SOFT_CHECKS:
            failed.append(field)
        else:
            warnings.append(field)

    vin = fields.get("vin")
    if vin:
        add("vin", vin_check_digit_valid(str(vin)), "vin_check_digit", "valid", str(vin), hard=False)
        wmi = str(vin)[:3]
        make = str(fields.get("make", ""))
        if wmi in WMI_MAKE and make:
            add(
                "vin",
                _make_matches_wmi(make, wmi),
                "wmi_make",
                WMI_MAKE[wmi],
                make,
                hard=False,
            )
        yc = str(vin)[9]
        if yc in YEAR_CHAR and fields.get("year"):
            add(
                "year",
                YEAR_CHAR[yc] == int(fields["year"]),
                "vin_year",
                str(YEAR_CHAR[yc]),
                str(fields["year"]),
                hard=False,
            )

    if fields.get("subtotal") and fields.get("total"):
        sub = Decimal(str(fields["subtotal"]))
        labor = Decimal(str(fields.get("labor_cost", 0)))
        tax = Decimal(str(fields.get("sales_tax", 0)))
        total = Decimal(str(fields["total"]))
        expected = sub + labor + tax
        diff = abs(expected - total)
        add("total", diff <= Decimal("2.00"), "invoice_sum", str(expected), str(total), 0.15, hard=False)

    eff = fields.get("effective_date")
    exp = fields.get("expiry_date")
    if isinstance(eff, date) and isinstance(exp, date):
        add("expiry_date", eff < exp, "date_order", "effective < expiry", f"{eff} vs {exp}")

    issue = fields.get("license_issue_date")
    lexp = fields.get("license_expiry_date")
    if isinstance(issue, date) and isinstance(lexp, date):
        add("license_expiry_date", issue < lexp, "cdl_dates", "issue < expiry", f"{issue} vs {lexp}")

    confidences = []
    for name, conf in field_confidences.items():
        penalty = 0.95 if name in warnings else 1.0
        confidences.append(min(l1_confidence, conf) * penalty)

    if confidences:
        overall = (min(confidences) * 0.5) + (sum(confidences) / len(confidences) * 0.5)
    else:
        overall = l1_confidence * 0.5

    return ValidationResult(
        overall_valid=len(failed) == 0,
        overall_confidence=round(overall, 2),
        field_results=field_results,
        needs_review=len(failed) > 0,
        failed_fields=failed,
    )
