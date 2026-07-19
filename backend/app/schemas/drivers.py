from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field



class DriverListItem(BaseModel):
    id: UUID
    driver_code: str | None = None
    full_name: str
    status: str
    current_truck_unit: int | None = None
    license_expiry_date: date
    license_class: str | None = None
    endorsements: str | None = None
    expiry_status: str = "green"


class DriverIdentity(BaseModel):
    full_name: str
    driver_code: str | None = None
    date_of_birth: date | None = None
    address: str | None = None
    sex: str | None = None
    height: str | None = None
    weight: int | None = None
    eye_color: str | None = None


class DriverLicense(BaseModel):
    number: str
    state: str
    license_class: str
    endorsements: str | None = None
    restrictions: str | None = None
    issue_date: date | None = None
    expiry_date: date
    expiry_status: str
    days_remaining: int


class CurrentDriverAssignmentInfo(BaseModel):
    truck_unit: int
    truck_make_model_year: str
    assigned_since: date
    days_assigned: int


class DriverAssignmentHistoryItem(BaseModel):
    truck_unit: int
    truck_make_model: str
    start_date: date
    end_date: date | None = None
    duration_days: int


class DriverProfileResponse(BaseModel):
    identity: DriverIdentity
    license: DriverLicense
    current_assignment: CurrentDriverAssignmentInfo | None = None
    assignment_history: list[DriverAssignmentHistoryItem] = Field(default_factory=list)
    total_trucks_operated: int = 0
    time_in_fleet_days: int = 0
    relationships_graph: dict[str, Any] = Field(default_factory=dict)
