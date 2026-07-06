"""Intent classification constants for the chat agent."""

from __future__ import annotations

ENTITY_OVERVIEW = "entity_overview"
SPECIFIC_METRIC = "specific_metric"
DOCUMENT_RETRIEVAL = "document_retrieval"
COMPARISON = "comparison"
COMPLIANCE_CHECK = "compliance_check"
EXPLANATION = "explanation"
TREND_ANALYSIS = "trend_analysis"
RELATIONSHIP_QUERY = "relationship_query"
HISTORY_RECALL = "history_recall"
ACTION_REQUEST = "action_request"
GREETING = "greeting"

ALL_INTENTS = frozenset(
    {
        ENTITY_OVERVIEW,
        SPECIFIC_METRIC,
        DOCUMENT_RETRIEVAL,
        COMPARISON,
        COMPLIANCE_CHECK,
        EXPLANATION,
        TREND_ANALYSIS,
        RELATIONSHIP_QUERY,
        HISTORY_RECALL,
        ACTION_REQUEST,
        GREETING,
    }
)
