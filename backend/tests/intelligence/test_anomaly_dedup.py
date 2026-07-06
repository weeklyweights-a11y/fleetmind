"""Tests for anomaly deduplication."""

from __future__ import annotations

import uuid

import pytest

from app.intelligence.anomalies.service import upsert_anomaly
from app.intelligence.schemas import AnomalyCandidate


@pytest.mark.asyncio
async def test_anomaly_dedup_active_duplicate():
    from app.database import async_session_factory

    truck_id = uuid.uuid4()
    candidate = AnomalyCandidate(
        anomaly_type="cost_spike",
        entity_type="truck",
        entity_id=truck_id,
        description="Test spike",
        severity="warning",
        supporting_data={"metric": "maintenance_monthly_spend"},
        dedup_key=f"cost_spike:truck:{truck_id}:maintenance_monthly_spend",
    )
    async with async_session_factory() as db:
        row1, created1 = await upsert_anomaly(db, candidate)
        assert created1 is True
        row2, created2 = await upsert_anomaly(db, candidate)
        assert created2 is False
        assert row2 is None
        await db.rollback()
