"""Shared intelligence layer types."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass
class BaselineSnapshot:
    entity_type: str
    entity_id: uuid.UUID | None
    metric_name: str
    value: Decimal
    period_type: str
    period_start: date
    period_end: date


@dataclass
class AnomalyCandidate:
    anomaly_type: str
    entity_type: str
    entity_id: uuid.UUID | None
    description: str
    severity: str
    supporting_data: dict[str, Any]
    dedup_key: str | None = None


@dataclass
class DetectionResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    candidates: list[AnomalyCandidate] = field(default_factory=list)


@dataclass
class JobRunSummary:
    process_name: str
    started_at: datetime
    finished_at: datetime | None = None
    entities_processed: int = 0
    anomalies_created: int = 0
    anomalies_updated: int = 0
    anomalies_resolved: int = 0
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)
