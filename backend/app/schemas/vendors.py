from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field



class VendorFleetItem(BaseModel):
    id: str
    name: str
    total_spend: Decimal
    event_count: int
    truck_count: int
    avg_cost: Decimal
    top_category: str | None = None


class VendorConcentration(BaseModel):
    top_vendor_pct: float
    top_3_pct: float
    total_vendors: int


class VendorFleetResponse(BaseModel):
    vendors: list[VendorFleetItem]
    concentration: VendorConcentration


class VendorDetailInfo(BaseModel):
    name: str
    address: str | None = None
    type: str


class VendorSummary(BaseModel):
    total_spend: Decimal
    event_count: int
    avg_cost: Decimal
    first_visit: date | None = None
    last_visit: date | None = None


class VendorByTruck(BaseModel):
    truck_unit: int
    count: int
    total_spend: Decimal


class VendorByCategory(BaseModel):
    category: str
    count: int
    total_spend: Decimal


class VendorTrendPoint(BaseModel):
    month: str
    spend: Decimal
    count: int


class VendorCostComparison(BaseModel):
    vendor_avg_cost: Decimal
    fleet_avg_cost: Decimal
    difference_pct: float


class VendorDetailResponse(BaseModel):
    vendor: VendorDetailInfo
    summary: VendorSummary
    by_truck: list[VendorByTruck] = Field(default_factory=list)
    by_category: list[VendorByCategory] = Field(default_factory=list)
    trend: list[VendorTrendPoint] = Field(default_factory=list)
    comparison: VendorCostComparison | None = None
    relationship_graph: dict[str, Any] = Field(default_factory=dict)
