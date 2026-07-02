"""Gemini Flash Vision extraction for image PDFs."""

from __future__ import annotations

import json
import logging

from app.enums import DocumentType
from app.extraction.types import ExtractionResult, ReadingResult
from app.services.gemini_client import generate_json_from_images

logger = logging.getLogger(__name__)

PROMPT = """This is a scanned fleet management document for Sunflower Freight Lines.
Identify the document type and extract structured fields.

Return JSON:
{
  "document_type": one of [
    "bill_of_sale_purchase", "bill_of_sale_sale", "cdl", "insurance_card",
    "service_invoice", "irp_cab_card", "title", "ifta_filing", "unknown"
  ],
  "fields": { ... extracted field names and values ... },
  "confidence": 0.0-1.0
}

Use these field names when present:
- Bills of sale: fleet_unit_no, vin, year, make, model, document_date, purchase_price, seller_name, buyer_name
- CDL: driver_code, full_name, license_number, license_class, license_issue_date, license_expiry_date, fleet_unit_assignment
- Insurance: policy_number, insurer_name, unit_number, vin, effective_date, expiry_date
- Invoice: invoice_number, invoice_date, unit_number, vin, vendor_name, category, total, subtotal
- IRP: plate_number, vin, unit_number, effective_date, expiry_date
- Title: title_number, vin, year, make, model, issue_date, owner_name
"""


async def extract_image(reading: ReadingResult, hint_type: str | None = None) -> ExtractionResult:
    if not reading.page_images:
        return ExtractionResult(
            document_type=hint_type or DocumentType.UNKNOWN.value,
            extracted_fields={},
            extraction_method="gemini_vision",
            field_confidences={},
            warnings=["No page images available"],
        )

    type_hint = ""
    if hint_type and hint_type != DocumentType.UNKNOWN.value:
        type_hint = f"\nThe expected document_type is: {hint_type}\n"

    prompt = PROMPT + type_hint

    try:
        raw = await generate_json_from_images(reading.page_images, prompt)
        data = json.loads(raw) if isinstance(raw, str) else raw
        dtype = data.get("document_type", hint_type or DocumentType.UNKNOWN.value)
        valid_types = {t.value for t in DocumentType}
        if dtype not in valid_types:
            dtype = hint_type or DocumentType.UNKNOWN.value
        if hint_type and hint_type in valid_types and dtype == DocumentType.UNKNOWN.value:
            dtype = hint_type
        fields = data.get("fields", {})
        conf = float(data.get("confidence", 0.75))
        field_confidences = {k: conf for k in fields}
        return ExtractionResult(
            document_type=dtype,
            extracted_fields=fields,
            extraction_method="gemini_vision",
            field_confidences=field_confidences,
        )
    except Exception as exc:
        logger.exception("Image vision extraction failed")
        return ExtractionResult(
            document_type=DocumentType.UNKNOWN.value,
            extracted_fields={},
            extraction_method="gemini_vision",
            field_confidences={},
            warnings=[str(exc)],
        )
