"""Document type classification."""

from __future__ import annotations

import re

from app.enums import DocumentType
from app.extraction.text_utils import collapse_spaced_text, extract_document_number
from app.extraction.types import LayoutResult, ReadingResult

INVOICE_PREFIXES = (
    "CSS-",
    "DEC-",
    "FLP-",
    "LTS-",
    "PSC-",
    "RPS-",
    "RTR-",
    "STM-",
    "TSI-",
    "VTW-",
    "WBP-",
    "ROA-",
    "LOV-",
    "PET-",
    "TA-",
)

# Image PDFs in the Sunflower dataset (no text layer) — mapped by filename.
IMAGE_PDF_TYPES: dict[str, str] = {
    "document_064.pdf": DocumentType.INSURANCE_CARD.value,
    "document_065.pdf": DocumentType.IRP_CAB_CARD.value,
    "document_066.pdf": DocumentType.SERVICE_INVOICE.value,
    "document_067.pdf": DocumentType.CDL.value,
    "document_068.pdf": DocumentType.TITLE.value,
}


def _filename_hint(file_path: str | None) -> str | None:
    if not file_path:
        return None
    name = file_path.replace("\\", "/").split("/")[-1].lower()
    return IMAGE_PDF_TYPES.get(name)


def _is_ifta_document(text: str, doc_num: str) -> bool:
    upper = text.upper()
    return (
        doc_num.startswith("IFTA-")
        or "INTERNATIONAL FUEL TAX" in upper
        or "FUEL TAX AGREEMENT" in upper
        or ("IFTA" in upper and "QUARTER" in upper)
        or "ALL MILES & GALLONS ROUNDED" in upper
    )


def classify_document(
    reading: ReadingResult,
    layout: LayoutResult,
    file_path: str | None = None,
) -> str:
    text = collapse_spaced_text(layout.full_text or reading.full_text)
    upper = text.upper()
    head = upper[:800]
    doc_num = extract_document_number(text) or ""

    if reading.source_format == "image_pdf":
        hinted = _filename_hint(file_path)
        if hinted:
            return hinted
        return DocumentType.UNKNOWN.value

    if doc_num.startswith("BOS-") or "BILL OF SALE" in head:
        if "(SALE)" in head or re.search(r"BOS-\d+-S\d+", doc_num, re.I):
            return DocumentType.BILL_OF_SALE_SALE.value
        return DocumentType.BILL_OF_SALE_PURCHASE.value

    if doc_num.startswith("CDL-") or ("SCANNED DOCUMENT" in head and "CDL" in head):
        return DocumentType.CDL.value

    if (
        "GWCA-" in doc_num
        or "INSURANCE IDENTIFICATION" in upper
        or "GREAT WEST CASUALTY" in upper
        or "INSURANCE ID CARD" in upper
    ):
        return DocumentType.INSURANCE_CARD.value

    # IFTA before generic INVOICE — IFTA filings may contain the word "invoice".
    if _is_ifta_document(text, doc_num):
        return DocumentType.IFTA_FILING.value

    if any(p in doc_num for p in INVOICE_PREFIXES) or (
        "INVOICE" in head and ("UNIT" in upper[:2000] or "VIN" in upper[:2000])
    ):
        return DocumentType.SERVICE_INVOICE.value

    if doc_num.startswith("KS-REG-") or ("APPORTIONED" in upper and "IRP" in upper):
        return DocumentType.IRP_CAB_CARD.value

    if (
        "CERTIFICATE OF TITLE" in upper
        or "TITLE NUMBER" in upper
        or "KANSAS TITLE" in upper
        or ("STATE OF KANSAS" in upper and "TITLE" in upper)
    ):
        return DocumentType.TITLE.value

    if "FORM 2290" in upper or "HEAVY HIGHWAY VEHICLE USE TAX" in upper:
        return DocumentType.FORM_2290.value

    return DocumentType.UNKNOWN.value


def classify_for_bulk_import(file_path: str, reading: ReadingResult | None = None) -> int:
    """Return wave number 1-4 for bulk import ordering."""
    from app.extraction.layer1_reader import read_document

    if reading is None:
        reading = read_document(file_path)
    layout_text = collapse_spaced_text(reading.full_text)
    head = layout_text[:500].upper()
    doc_num = extract_document_number(layout_text) or ""

    if doc_num.startswith("BOS-") or "BILL OF SALE" in head:
        if "(SALE)" in head or re.search(r"BOS-\d+-S\d+", doc_num, re.I):
            return 3
        return 1
    if "SCANNED DOCUMENT" in head and "CDL" in head:
        return 2
    return 4
