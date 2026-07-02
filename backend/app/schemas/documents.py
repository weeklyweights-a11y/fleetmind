from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    postgres: str
    redis: str
    neo4j: str
    status: str = "ok"


class DocumentUploadResponse(BaseModel):
    document_id: UUID
    status: str


class BatchUploadError(BaseModel):
    filename: str
    error_code: str
    message: str


class DocumentBatchUploadResponse(BaseModel):
    document_ids: list[UUID]
    errors: list[BatchUploadError] = Field(default_factory=list)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: int
    original_filename: str
    file_path: str
    file_size_bytes: int | None
    page_count: int | None
    source_format: str
    parse_method: str | None
    document_type: str | None
    document_number: str | None
    document_date: date | None
    truck_id: UUID | None
    driver_id: UUID | None
    vendor_id: UUID | None
    truck_unit: int | None = None
    processing_status: str
    parse_confidence: Decimal | None
    entity_resolution_confidence: Decimal | None
    review_status: str | None
    review_notes: str | None
    error_details: str | None
    created_at: datetime
    updated_at: datetime


class DocumentExtractionField(BaseModel):
    name: str
    value: Any
    confidence: float | None = None
    corrected: bool = False
    correction_source: str | None = None
    validation_error: str | None = None


class DocumentExtractionResponse(BaseModel):
    document_id: UUID
    document_type: str | None = None
    fields: list[DocumentExtractionField] = Field(default_factory=list)
    validation_failures: list[dict[str, str]] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentCorrectionItem(BaseModel):
    field_name: str
    corrected_value: str


class DocumentReviewSubmitRequest(BaseModel):
    action: Literal["correct", "approve", "reject"] = "correct"
    corrections: list[DocumentCorrectionItem] = Field(default_factory=list)
    corrected_by: str | None = None
    reprocess: bool = False
    reject_reason: str | None = None


class DocumentReviewSubmitResponse(BaseModel):
    document_id: UUID
    review_status: str
    corrections_applied: int
    requeued: bool


class DocumentReviewListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
