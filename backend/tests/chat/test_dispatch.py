"""Dispatch registry tests."""

from datetime import date

from app.chat.dispatch import DISPATCH_REGISTRY, _parse_date


def test_registry_has_phase5_and_phase6_callables():
    assert len(DISPATCH_REGISTRY) >= 20
    assert "get_truck_maintenance" in DISPATCH_REGISTRY
    assert "get_memory_search" in DISPATCH_REGISTRY
    assert "update_anomaly_status" in DISPATCH_REGISTRY


def test_parse_date():
    assert _parse_date("2025-01-01") == date(2025, 1, 1)
