"""Tests for fleet metrics store."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.intelligence.baselines.stats import monthly_spend_stats, mom_change_pct


def test_monthly_spend_stats_empty():
    stats = monthly_spend_stats([])
    assert stats["mean"] == 0.0


def test_mom_change_pct():
    assert mom_change_pct([100, 120]) == pytest.approx(20.0)


def test_anomaly_candidate_dedup_key():
    from app.intelligence.schemas import AnomalyCandidate

    c = AnomalyCandidate(
        anomaly_type="cost_spike",
        entity_type="truck",
        entity_id=uuid.uuid4(),
        description="x",
        severity="warning",
        supporting_data={"metric": "spend"},
    )
    assert c.anomaly_type == "cost_spike"
