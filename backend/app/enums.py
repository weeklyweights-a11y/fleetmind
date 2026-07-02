from datetime import datetime
from enum import StrEnum


class ProcessingStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    NORMALIZING = "normalizing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class SourceFormat(StrEnum):
    TEXT_PDF = "text_pdf"
    IMAGE_PDF = "image_pdf"
    PHOTO = "photo"
    TEXT = "text"


class DocumentType(StrEnum):
    BILL_OF_SALE_PURCHASE = "bill_of_sale_purchase"
    BILL_OF_SALE_SALE = "bill_of_sale_sale"
    CDL = "cdl"
    INSURANCE_CARD = "insurance_card"
    SERVICE_INVOICE = "service_invoice"
    IRP_CAB_CARD = "irp_cab_card"
    TITLE = "title"
    IFTA_FILING = "ifta_filing"
    FORM_2290 = "form_2290"
    UNKNOWN = "unknown"


class TruckStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SOLD = "sold"
    SCRAPPED = "scrapped"


class DisposalType(StrEnum):
    SOLD = "sold"
    SCRAPPED = "scrapped"
    TRADED = "traded"
    TOTALED = "totaled"
