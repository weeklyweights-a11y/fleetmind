"""Chat agent unit tests."""

from app.chat.intents import ALL_INTENTS, ENTITY_OVERVIEW
from app.chat.schemas import QueryUnderstanding, TurnState


def test_intents_complete():
    assert ENTITY_OVERVIEW in ALL_INTENTS
    assert len(ALL_INTENTS) == 11


def test_turn_state_defaults():
    ts = TurnState()
    assert ts.turn_history == []


def test_query_understanding_schema():
    qu = QueryUnderstanding(confidence=0.9, intent="greeting")
    assert qu.intent == "greeting"


def test_edge_case_prompts_present():
    from app.chat.prompts import load_prompt

    text = load_prompt("query_understanding.txt") + load_prompt("response_synthesis.txt")
    for snippet in ("Ambiguous entity", "Forecasting", "action_request", "If data missing", "contradicts"):
        assert snippet.lower() in text.lower()

