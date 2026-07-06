"""Orchestrator routing unit tests."""

from app.chat.orchestrator import route_after_understand
from app.chat.schemas import ChatGraphState, QueryUnderstanding


def test_route_low_confidence_to_clarify():
    state: ChatGraphState = {
        "query_understanding": QueryUnderstanding(confidence=0.3, intent="entity_overview"),
    }
    assert route_after_understand(state) == "clarify"


def test_route_high_confidence_to_dispatch():
    state: ChatGraphState = {
        "query_understanding": QueryUnderstanding(confidence=0.85, intent="entity_overview"),
    }
    assert route_after_understand(state) == "dispatch_agents"


def test_route_missing_understanding_defaults_dispatch():
    state: ChatGraphState = {}
    assert route_after_understand(state) == "dispatch_agents"
