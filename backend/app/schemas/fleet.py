from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import GraphEdge, GraphNode


class FleetComposition(BaseModel):
    total_trucks: int
    active: int
    sold: int
    inactive: int
    total_drivers: int
    assigned_drivers: int
    unassigned_drivers: int
    total_fleet_value: Decimal
    avg_truck_age: float


class ComplianceSnapshot(BaseModel):
    fully_compliant: int
    warnings: int
    expirations: int
    incomplete: int
    urgent_items: list[dict[str, Any]] = Field(default_factory=list)


class FinancialSnapshot(BaseModel):
    this_month_spend: Decimal
    last_month_spend: Decimal
    three_month_avg: Decimal
    mom_change_pct: float | None = None
    total_fleet_tco: Decimal


class RecentActivityItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    document_id: UUID
    type: str | None = None
    truck_unit: int | None = None
    activity_date: date | None = Field(None, serialization_alias="date")
    status: str
    description: str | None = None
    created_at: datetime | None = None


class QuickStats(BaseModel):
    total_maintenance_events: int
    total_vendors: int
    most_expensive_truck: dict[str, Any] | None = None
    most_serviced_truck: dict[str, Any] | None = None
    fleet_avg_cost_per_mile: Decimal | None = None


class FleetOverviewResponse(BaseModel):
    fleet_composition: FleetComposition
    compliance_snapshot: ComplianceSnapshot
    financial_snapshot: FinancialSnapshot
    recent_activity: list[RecentActivityItem] = Field(default_factory=list)
    review_queue_count: int = 0
    quick_stats: QuickStats


class FleetComparisonTruck(BaseModel):
    truck_id: UUID
    unit_number: int
    make_model_year: str
    driver_name: str | None = None
    tco: Decimal
    maintenance_spend: Decimal
    event_count: int
    cost_per_mile: Decimal | None = None
    top_category: str | None = None
    compliance_status: str
    age_years: float
    outlier_flags: list[str] = Field(default_factory=list)


class FleetComparisonRankings(BaseModel):
    by_tco: list[int] = Field(default_factory=list)
    by_maintenance: list[int] = Field(default_factory=list)
    by_cost_per_mile: list[int] = Field(default_factory=list)


class FleetAverages(BaseModel):
    avg_tco: Decimal
    avg_maintenance: Decimal
    avg_events: float
    avg_cost_per_mile: Decimal | None = None


class FleetComparisonResponse(BaseModel):
    trucks: list[FleetComparisonTruck]
    rankings: FleetComparisonRankings
    fleet_averages: FleetAverages


class FleetGraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    stats: dict[str, int]


class FleetMaintenanceMonthPoint(BaseModel):
    month: str
    spend: Decimal
    event_count: int


class FleetCategorySpend(BaseModel):
    category: str
    spend: Decimal
    count: int


class FleetMaintenanceSummaryResponse(BaseModel):
    monthly_trend: list[FleetMaintenanceMonthPoint] = Field(default_factory=list)
    by_category: list[FleetCategorySpend] = Field(default_factory=list)
