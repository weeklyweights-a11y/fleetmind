from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnomalyItem(BaseModel):
    anomaly_id: UUID
    type: str
    entity_type: str
    entity_id: UUID | None = None
    entity_name: str | None = None
    description: str
    severity: str
    supporting_data: dict[str, Any] | list[Any] = Field(default_factory=dict)
    status: str
    detected_at: datetime
    follow_up: bool = False
    conversation_id: UUID | None = None


class AnomalyStatusUpdate(BaseModel):
    status: str
    reason: str | None = None
    operator_name: str | None = "default"


class AnomalyCounts(BaseModel):
    total: int
    new: int
    acknowledged: int
    investigating: int


class AnomalyFeedResponse(BaseModel):
    anomalies: list[AnomalyItem] = Field(default_factory=list)
    counts: AnomalyCounts
