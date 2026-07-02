from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    ComplianceCategoryDetail,
    GraphEdge,
    GraphNode,
    OverallComplianceStatus,
)


class TruckListItem(BaseModel):
    id: UUID
    unit_number: int
    vin: str
    year: int
    make: str
    model: str
    status: str
    current_driver_name: str | None = None


class OdometerReading(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reading: int
    record_date: date = Field(serialization_alias="date")
    source_type: str


class TruckIdentityResponse(BaseModel):
    id: UUID
    unit_number: int
    vin: str
    year: int
    make: str
    model: str
    body_type: str | None = None
    color: str | None = None
    fuel_type: str | None = None
    gross_vehicle_weight: int | None = None
    status: str
    acquired_date: date | None = None
    purchase_price: Decimal | None = None
    acquired_from_vendor: str | None = None
    initial_odometer: int | None = None
    disposed_date: date | None = None
    sale_price: Decimal | None = None
    disposed_to: str | None = None
    disposal_type: str | None = None
    current_odometer: OdometerReading | None = None
    estimated_current_miles: int | None = None
    age_years: float | None = None
    time_in_fleet_days: int | None = None


class CurrentDriverAssignment(BaseModel):
    driver_id: UUID
    full_name: str
    driver_code: str | None = None
    license_number: str
    license_class: str
    license_expiry_date: date
    license_expiry_status: str
    endorsements: str | None = None
    restrictions: str | None = None
    assigned_since: date
    assignment_type: str
    days_assigned: int


class PreviousDriverAssignment(BaseModel):
    full_name: str
    driver_code: str | None = None
    start_date: date
    end_date: date
    duration_days: int
    assignment_type: str


class TruckAssignmentResponse(BaseModel):
    current_driver: CurrentDriverAssignment | None = None
    unassigned_reason: str | None = None
    previous_drivers: list[PreviousDriverAssignment] = Field(default_factory=list)
    total_drivers_historically: int = 0
    assignment_stability: str = "unknown"
    assignment_chain: list[GraphEdge] = Field(default_factory=list)


class MaintenanceSummary(BaseModel):
    total_spend: Decimal
    event_count: int
    avg_cost: Decimal
    min_cost: Decimal
    max_cost: Decimal


class LastService(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    service_date: date = Field(serialization_alias="date")
    vendor_name: str
    category: str
    description: str
    cost: Decimal
    days_ago: int


class CategoryBreakdown(BaseModel):
    category: str
    count: int
    total_spend: Decimal
    pct_of_total: float


class VendorBreakdown(BaseModel):
    vendor_name: str
    count: int
    total_spend: Decimal
    avg_cost: Decimal
    last_visit: date | None = None


class FleetMaintenanceComparison(BaseModel):
    fleet_avg_total: Decimal
    this_truck_total: Decimal
    ratio: float
    rank_in_fleet: int
    fleet_avg_per_event: Decimal
    fleet_avg_frequency: float


class MaintenanceTrendPoint(BaseModel):
    month: str
    total_spend: Decimal
    event_count: int


class MaintenancePattern(BaseModel):
    pattern_type: str
    description: str
    supporting_data: dict[str, Any] = Field(default_factory=dict)


class TruckMaintenanceResponse(BaseModel):
    summary: MaintenanceSummary
    last_service: LastService | None = None
    by_category: list[CategoryBreakdown] = Field(default_factory=list)
    by_vendor: list[VendorBreakdown] = Field(default_factory=list)
    fleet_comparison: FleetMaintenanceComparison
    trend: list[MaintenanceTrendPoint] = Field(default_factory=list)
    patterns: list[MaintenancePattern] = Field(default_factory=list)
    vendor_graph: dict[str, Any] = Field(default_factory=dict)


class ComplianceCategories(BaseModel):
    insurance: ComplianceCategoryDetail
    registration: ComplianceCategoryDetail
    title: ComplianceCategoryDetail
    emission: ComplianceCategoryDetail
    driver_cdl: ComplianceCategoryDetail
    medical_cert: ComplianceCategoryDetail


class UrgentComplianceItem(BaseModel):
    category: str
    status: str
    days_remaining: int | None = None
    expiry_date: str | None = None
    description: str | None = None


class TruckComplianceResponse(BaseModel):
    overall_status: OverallComplianceStatus
    categories: ComplianceCategories
    urgent_items: list[UrgentComplianceItem] = Field(default_factory=list)


class AcquisitionInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    price: Decimal | None = None
    acquisition_date: date | None = Field(None, serialization_alias="date")
    seller: str | None = None
    initial_odometer: int | None = None


class CostBreakdown(BaseModel):
    acquisition_pct: float
    maintenance_pct: float
    registration_pct: float
    insurance_pct: float


class BookValue(BaseModel):
    original: Decimal | None = None
    depreciated: Decimal | None = None
    years_owned: float | None = None
    depreciation_method: str = "straight_line_10yr"


class FleetFinancialComparison(BaseModel):
    fleet_avg_tco: Decimal
    rank: int
    fleet_avg_cost_per_mile: Decimal | None = None
    cost_per_mile_rank: int | None = None


class ProfitabilityEstimate(BaseModel):
    revenue_per_mile: Decimal
    estimated_revenue: Decimal
    margin: Decimal | None = None


class TruckFinancialsResponse(BaseModel):
    acquisition: AcquisitionInfo
    maintenance_total: Decimal
    registration_total: Decimal
    insurance_total: Decimal | None = None
    total_cost_of_ownership: Decimal
    cost_breakdown: CostBreakdown
    cost_per_mile: Decimal | None = None
    monthly_cost_rate: Decimal
    book_value: BookValue
    fleet_comparison: FleetFinancialComparison
    total_miles_driven: int | None = None
    profitability_estimate: ProfitabilityEstimate | None = None


class TruckDocumentItem(BaseModel):
    document_id: UUID
    document_number: str | None = None
    document_date: date | None = None
    filename: str
    file_path: str
    status: str
    confidence: Decimal | None = None


class DocumentTypeGroup(BaseModel):
    count: int
    documents: list[TruckDocumentItem]


class TruckDocumentsResponse(BaseModel):
    total_documents: int
    by_type: dict[str, DocumentTypeGroup]
    timeline: list[TruckDocumentItem] = Field(default_factory=list)
    related_documents: list[TruckDocumentItem] = Field(default_factory=list)


class TruckGraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    center_node: str
