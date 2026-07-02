from typing import Any, Literal

from pydantic import BaseModel, Field

ComplianceStatusColor = Literal["green", "yellow", "red", "grey"]
OverallComplianceStatus = Literal["compliant", "attention_needed", "non_compliant", "incomplete"]


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ComplianceCell(BaseModel):
    status: ComplianceStatusColor
    days: int | None = None
    expiry: str | None = None
    driver_name: str | None = None


class ComplianceCategoryDetail(BaseModel):
    status: ComplianceStatusColor
    policy_number: str | None = None
    insurer: str | None = None
    effective_date: str | None = None
    expiry_date: str | None = None
    days_remaining: int | None = None
    plate_number: str | None = None
    registration_number: str | None = None
    title_number: str | None = None
    issue_date: str | None = None
    lien_holder: str | None = None
    last_test_date: str | None = None
    result: str | None = None
    next_due_date: str | None = None
    driver_name: str | None = None
    license_number: str | None = None
    note: str | None = None
    source_document_id: str | None = None
