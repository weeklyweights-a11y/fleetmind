"""Layer 2: Layout understanding (heuristic + optional Docling)."""

from __future__ import annotations

import re

from app.extraction.text_utils import collapse_spaced_text, normalize_whitespace
from app.extraction.types import LayoutResult, LayoutSection, ReadingResult


def _heuristic_layout(reading: ReadingResult) -> LayoutResult:
    text = collapse_spaced_text(reading.full_text)
    lines = [normalize_whitespace(ln) for ln in text.splitlines() if ln.strip()]

    header_lines = lines[:8]
    footer_lines = lines[-6:] if len(lines) > 6 else []
    header_block = "\n".join(header_lines)
    footer_block = "\n".join(footer_lines)

    document_title = None
    for ln in lines[:15]:
        if re.search(r"BILL OF SALE|COMMERCIAL DRIVER|INVOICE|CERTIFICATE OF TITLE|IFTA|IRP", ln, re.I):
            document_title = ln
            break

    sections: list[LayoutSection] = []
    current_name = "body"
    current_lines: list[str] = []

    for ln in lines:
        if re.match(r"^[A-Z][A-Z\s/&]{4,}$", ln) and len(ln) < 80:
            if current_lines:
                sections.append(LayoutSection(name=current_name, content="\n".join(current_lines)))
            current_name = ln.lower()[:50]
            current_lines = []
        else:
            current_lines.append(ln)
    if current_lines:
        sections.append(LayoutSection(name=current_name, content="\n".join(current_lines)))

    return LayoutResult(
        document_title=document_title,
        sections=sections,
        header_block=header_block,
        footer_block=footer_block,
        full_text=text,
    )


def build_layout(reading: ReadingResult) -> LayoutResult:
    # Docling optional — heuristic fallback is sufficient for Sunflower templates.
    try:
        from docling.document_converter import DocumentConverter  # noqa: F401

        # MVP: still use heuristic for speed/reliability in Docker CPU.
        return _heuristic_layout(reading)
    except ImportError:
        return _heuristic_layout(reading)
