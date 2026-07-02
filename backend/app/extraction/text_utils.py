"""Text utilities for rule-based extraction."""

from __future__ import annotations

import re
from typing import Any


def collapse_spaced_text(text: str) -> str:
    """Collapse letter-spaced PDF text like 'T R U C K' -> 'TRUCK'."""
    if not text:
        return text

    def _collapse_segment(segment: str) -> str:
        parts = segment.split(" ")
        if len(parts) >= 3 and all(len(p) <= 2 for p in parts if p):
            single_char_runs = sum(1 for p in parts if len(p) == 1)
            if single_char_runs >= 3:
                return "".join(parts)
        return segment

    return " ".join(_collapse_segment(s) for s in re.split(r"(\s{2,})", text))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def meaningful_char_count(text: str) -> int:
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        if re.search(r"page\s+\d+\s+of\s+\d+", stripped, re.I):
            continue
        if len(stripped) < 4 and stripped.isupper():
            continue
        kept.append(stripped)
    collapsed = normalize_whitespace(" ".join(kept))
    return sum(1 for c in collapsed if c.isalnum())


def find_first_match(patterns: list[str], text: str, flags: int = re.I) -> str | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return None


def find_label_value(text: str, labels: list[str], pattern: str | None = None) -> str | None:
    collapsed = collapse_spaced_text(text)
    for label in labels:
        label_pat = re.escape(label).replace(r"\ ", r"\s*")
        if pattern:
            regex = rf"{label_pat}\s*[:.]?\s*({pattern})"
        else:
            regex = rf"{label_pat}\s*[:.]?\s*([^\n]+)"
        m = re.search(regex, collapsed, re.I)
        if m:
            return m.group(1).strip()
    return None


def parse_money(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"[\$]?\s*([\d,]+\.\d{2})", value.replace(" ", ""))
    return m.group(1) if m else None


def parse_int_from_text(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"([\d,]+)", value.replace(" ", ""))
    return m.group(1).replace(",", "") if m else None


def extract_vin(text: str) -> str | None:
    collapsed = collapse_spaced_text(text).upper()
    m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", collapsed)
    return m.group(1) if m else None


def extract_document_number(text: str) -> str | None:
    patterns = [
        r"(BOS-[A-Z0-9-]+)",
        r"(CDL-D\d+)",
        r"(GWCA-[A-Z0-9 -]+)",
        r"INVOICE\s*NO\.?\s*([A-Z]{3}-\d+)",
        r"(KS-REG-[A-Z0-9-]+)",
        r"(IFTA-[A-Z0-9-]+)",
        r"TITLE\s*NUMBER\s*([A-Z0-9]+)",
    ]
    return find_first_match(patterns, collapse_spaced_text(text))


def fields_from_labels(
    text: str,
    schema_fields: dict[str, dict[str, Any]],
) -> tuple[dict[str, str], dict[str, float]]:
    collapsed = collapse_spaced_text(text)
    fields: dict[str, str] = {}
    confidences: dict[str, float] = {}
    for name, spec in schema_fields.items():
        labels = spec.get("labels", [])
        pattern = spec.get("pattern")
        value = find_label_value(collapsed, labels, pattern)
        if value is None and spec.get("regex"):
            m = re.search(spec["regex"], collapsed, re.I)
            value = m.group(1).strip() if m else None
        if value is not None:
            fields[name] = value
            confidences[name] = 1.0 if labels else 0.8
    return fields, confidences
