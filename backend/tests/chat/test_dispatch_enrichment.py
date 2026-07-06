"""Dispatch enrichment rule tests."""

from __future__ import annotations

import pytest

from app.chat.dispatch_enrichment import enrich_query_understanding
from app.chat.schemas import DashboardContext, DispatchPlanItem, QueryUnderstanding


@pytest.mark.asyncio
async def test_enrich_worry_about_fleet():
    qu = QueryUnderstanding(confidence=0.5, dispatch_plan=[])
    state = {
        "message": "anything I should worry about right now",
        "dashboard_context": DashboardContext(),
    }
    result = await enrich_query_understanding(state, qu)
    assert any(p.function == "get_anomaly_feed" for p in result.dispatch_plan)
    assert result.confidence >= 0.75


@pytest.mark.asyncio
async def test_enrich_tracking():
    qu = QueryUnderstanding(confidence=0.4, dispatch_plan=[])
    state = {"message": "anything I was tracking", "dashboard_context": DashboardContext()}
    result = await enrich_query_understanding(state, qu)
    fns = {p.function for p in result.dispatch_plan}
    assert "get_tracking_items" in fns
    assert "get_memory_search" in fns


@pytest.mark.asyncio
async def test_enrich_greeting():
    qu = QueryUnderstanding(
        confidence=0.4,
        dispatch_plan=[DispatchPlanItem(function="get_fleet_overview", params={})],
    )
    state = {"message": "good morning", "dashboard_context": DashboardContext()}
    result = await enrich_query_understanding(state, qu)
    assert result.intent == "greeting"
    assert result.dispatch_plan == []
