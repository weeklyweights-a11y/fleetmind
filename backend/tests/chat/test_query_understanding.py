"""Query understanding tests with mocked Gemini."""

from __future__ import annotations

import pytest

from app.chat.schemas import ChatGraphState, DashboardContext
from app.chat import query_understanding as qu_mod


@pytest.mark.asyncio
async def test_understand_query_parses_json(monkeypatch):
    async def fake_generate_json(prompt: str) -> dict:
        return {
            "entities": [{"type": "truck", "identifier": "19", "resolved_name": "Truck 19"}],
            "time_scope": {"scope_description": "all time"},
            "intent": "entity_overview",
            "dispatch_plan": [{"function": "get_truck_identity", "params": {"unit": 19}}],
            "response_guidance": "overview",
            "confidence": 0.92,
        }

    monkeypatch.setattr(qu_mod, "generate_json", fake_generate_json)
    state: ChatGraphState = {
        "message": "tell me about truck 19",
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "operator_name": "default",
        "dashboard_context": DashboardContext(),
        "conversation_context": None,
        "recent_summaries": [],
        "operator_profile": None,
    }
    result = await qu_mod.understand_query(state)
    assert result.intent == "entity_overview"
    assert result.confidence >= 0.9
    assert result.dispatch_plan[0].function == "get_truck_identity"
