"""Layer 3: Field extraction dispatcher."""

from __future__ import annotations

from app.enums import DocumentType
from app.extraction.extractors import (
    bill_of_sale,
    cdl,
    form_2290,
    ifta_filing,
    image_vision,
    insurance_card,
    irp_cab_card,
    service_invoice,
    title,
)
from app.extraction.types import ExtractionResult, LayoutResult, ReadingResult


async def extract_fields(
    document_type: str,
    reading: ReadingResult,
    layout: LayoutResult,
) -> ExtractionResult:
    if reading.source_format == "image_pdf":
        result = await image_vision.extract_image(reading, hint_type=document_type)
        # Filename-mapped image PDFs (064–068): trust classifier hint over vision guess.
        if document_type != DocumentType.UNKNOWN.value:
            result.document_type = document_type
        if result.extracted_fields:
            return result
        return result

    if document_type == DocumentType.BILL_OF_SALE_PURCHASE.value:
        return bill_of_sale.extract(layout, document_type)
    if document_type == DocumentType.BILL_OF_SALE_SALE.value:
        return bill_of_sale.extract(layout, document_type)
    if document_type == DocumentType.CDL.value:
        return cdl.extract(layout)
    if document_type == DocumentType.INSURANCE_CARD.value:
        return insurance_card.extract(layout)
    if document_type == DocumentType.SERVICE_INVOICE.value:
        return service_invoice.extract(layout)
    if document_type == DocumentType.IRP_CAB_CARD.value:
        return irp_cab_card.extract(layout)
    if document_type == DocumentType.TITLE.value:
        return title.extract(layout)
    if document_type == DocumentType.IFTA_FILING.value:
        return ifta_filing.extract(layout)
    if document_type == DocumentType.FORM_2290.value:
        return form_2290.extract(layout)

    return ExtractionResult(
        document_type=document_type,
        extracted_fields={},
        extraction_method="rule_based",
        field_confidences={},
        warnings=[f"No extractor for type {document_type}"],
    )
