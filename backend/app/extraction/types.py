"""Shared types for the extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PositionedBlock:
    page: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass
class ReadingResult:
    source_format: str
    page_count: int
    full_text: str
    positioned_blocks: list[PositionedBlock]
    page_images: list[Any] = field(default_factory=list)
    parse_confidence: float = 1.0
    parse_method: str | None = None


@dataclass
class LayoutSection:
    name: str
    content: str
    region_type: str = "paragraph"


@dataclass
class LayoutResult:
    document_title: str | None
    sections: list[LayoutSection]
    header_block: str
    footer_block: str
    full_text: str


@dataclass
class ExtractionResult:
    document_type: str
    extracted_fields: dict[str, Any]
    extraction_method: str
    field_confidences: dict[str, float]
    warnings: list[str] = field(default_factory=list)


@dataclass
class NormalizationIssue:
    field_name: str
    raw_value: str
    error_description: str


@dataclass
class FieldValidationResult:
    valid: bool
    check_type: str
    expected: str
    actual: str
    confidence_impact: float


@dataclass
class ValidationResult:
    overall_valid: bool
    overall_confidence: float
    field_results: dict[str, FieldValidationResult]
    needs_review: bool
    failed_fields: list[str] = field(default_factory=list)


@dataclass
class CorrectionAttempt:
    field: str
    original: str
    proposed: str
    accepted: bool


@dataclass
class PipelineContext:
    document_id: str
    file_path: str
    original_filename: str
    tenant_id: int = 1
    l1: ReadingResult | None = None
    l2: LayoutResult | None = None
    extraction: ExtractionResult | None = None
    normalized_fields: dict[str, Any] = field(default_factory=dict)
    normalization_issues: list[NormalizationIssue] = field(default_factory=list)
    validation: ValidationResult | None = None
    l6_attempts: list[CorrectionAttempt] = field(default_factory=list)
    entity_resolution_confidence: float = 1.0
    affected_tables: list[str] = field(default_factory=list)
    normalized_record_ids: list[dict[str, str]] = field(default_factory=list)
    resolution_issues: list[str] = field(default_factory=list)
    inference_notes: list[str] = field(default_factory=list)
    truck_id: str | None = None
    driver_id: str | None = None
    vendor_id: str | None = None
    ifta_filing_id: str | None = None
    insurance_coverage_id: str | None = None
    ifta_vehicle_graph: list[dict[str, Any]] = field(default_factory=list)
