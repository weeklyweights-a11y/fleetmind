from pydantic import BaseModel, Field

from app.schemas.common import ComplianceCell, ComplianceStatusColor


class ComplianceMatrixRow(BaseModel):
    truck_unit: int
    truck_make_model: str
    insurance: ComplianceCell
    registration: ComplianceCell
    title: ComplianceCell
    emission: ComplianceCell
    driver_cdl: ComplianceCell
    medical_cert: ComplianceCell


class ComplianceDeadline(BaseModel):
    truck_unit: int
    compliance_type: str
    expiry_date: str
    days_remaining: int
    severity: ComplianceStatusColor


class ComplianceMatrixSummary(BaseModel):
    green_count: int
    yellow_count: int
    red_count: int
    grey_count: int


class ComplianceMatrixResponse(BaseModel):
    matrix: list[ComplianceMatrixRow]
    deadlines: list[ComplianceDeadline] = Field(default_factory=list)
    fleet_compliance_score: float
    summary: ComplianceMatrixSummary
