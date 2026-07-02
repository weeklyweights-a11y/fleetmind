"""Map document NOTIFY payloads to WebSocket topic names."""

from __future__ import annotations

from typing import Any

from app.enums import DocumentType

FLEET_TOPICS = ["fleet_stats", "compliance_overview", "recent_documents"]
COMPLIANCE_TOPICS = ["compliance_matrix", "compliance_overview"]


def _truck_topics(unit: int, suffixes: list[str]) -> list[str]:
    return [f"truck_{unit}_{s}" for s in suffixes]


def topics_for_document_event(payload: dict[str, Any]) -> list[str]:
    """Return all topics that may need a delta push for this NOTIFY payload."""
    topics: set[str] = {"document_status"}
    status = str(payload.get("status", ""))
    if status not in {"complete", "needs_review", "failed"} and payload.get("event_type") != "review":
        return list(topics)

    truck_unit = payload.get("truck_unit")
    if truck_unit is None and payload.get("truck_id"):
        # Unit resolved upstream when possible; skip truck-specific topics without unit
        pass
    elif truck_unit is not None:
        unit = int(truck_unit)
        doc_type = payload.get("document_type") or ""

        topics.update(_truck_topics(unit, ["documents", "financials"]))

        if doc_type in (
            DocumentType.BILL_OF_SALE_PURCHASE.value,
            DocumentType.BILL_OF_SALE_SALE.value,
        ):
            topics.update(_truck_topics(unit, ["identity", "assignment", "financials"]))
        elif doc_type == DocumentType.SERVICE_INVOICE.value:
            topics.update(_truck_topics(unit, ["maintenance"]))
        elif doc_type in (
            DocumentType.INSURANCE_CARD.value,
            DocumentType.IRP_CAB_CARD.value,
            DocumentType.TITLE.value,
            DocumentType.FORM_2290.value,
        ):
            topics.update(_truck_topics(unit, ["compliance"]))
        elif doc_type == DocumentType.CDL.value:
            topics.update(_truck_topics(unit, ["assignment", "compliance"]))
        else:
            topics.update(_truck_topics(unit, ["identity", "maintenance", "compliance"]))

    topics.update(FLEET_TOPICS)

    doc_type = payload.get("document_type") or ""
    if doc_type in (
        DocumentType.INSURANCE_CARD.value,
        DocumentType.IRP_CAB_CARD.value,
        DocumentType.TITLE.value,
        DocumentType.CDL.value,
        DocumentType.FORM_2290.value,
    ):
        topics.update(COMPLIANCE_TOPICS)

    driver_code = payload.get("driver_code")
    if driver_code:
        topics.add(f"driver_{driver_code}_profile")

    topics.add("anomalies")
    return sorted(topics)
