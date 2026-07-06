"""Compute and push WebSocket data_update deltas for subscribed topics."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.agents.compliance_matrix import get_compliance_matrix
from app.agents.fleet_overview import get_fleet_overview
from app.agents.truck_assignment import get_truck_assignment
from app.agents.truck_compliance import get_truck_compliance
from app.agents.truck_documents import get_truck_documents
from app.agents.truck_financials import get_truck_financials
from app.agents.truck_identity import get_truck_identity
from app.agents.truck_maintenance import get_truck_maintenance
from app.database import async_session_factory
from app.models.truck import Truck
from app.redis_client import get_subscribers_for_topics, get_topic_cache, set_topic_cache
from app.websocket.events import build_data_update_message
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

_STRUCTURAL_TOPICS = {
    "recent_documents",
    "compliance_matrix",
    "truck_",
}


async def _resolve_truck_uuid(unit: int, tenant_id: int = 1) -> uuid.UUID | None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Truck.id).where(Truck.tenant_id == tenant_id, Truck.unit_number == unit)
        )
        return result.scalar_one_or_none()


def _parse_truck_topic(topic: str) -> tuple[int, str] | None:
    if not topic.startswith("truck_"):
        return None
    parts = topic.split("_", 2)
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


async def _fetch_topic_data(topic: str, tenant_id: int = 1) -> dict[str, Any] | None:
    async with async_session_factory() as db:
        if topic == "fleet_stats":
            overview = await get_fleet_overview(db, tenant_id)
            return {
                "fleet_composition": overview.fleet_composition.model_dump(mode="json"),
                "financial_snapshot": overview.financial_snapshot.model_dump(mode="json"),
                "quick_stats": overview.quick_stats.model_dump(mode="json"),
            }
        if topic == "compliance_overview":
            overview = await get_fleet_overview(db, tenant_id)
            return overview.compliance_snapshot.model_dump(mode="json")
        if topic == "recent_documents":
            overview = await get_fleet_overview(db, tenant_id)
            return {
                "recent_activity": [i.model_dump(mode="json") for i in overview.recent_activity],
            }
        if topic == "compliance_matrix":
            matrix = await get_compliance_matrix(db, tenant_id)
            return matrix.model_dump(mode="json")
        if topic == "anomalies":
            from app.agents.anomaly_feed import get_anomaly_feed

            feed = await get_anomaly_feed(db, limit=3, tenant_id=tenant_id)
            return {
                "refetch": True,
                "counts": feed.counts.model_dump(mode="json"),
                "anomalies": [a.model_dump(mode="json") for a in feed.anomalies],
            }

        parsed = _parse_truck_topic(topic)
        if parsed is None:
            return None
        unit, suffix = parsed
        truck_id = await _resolve_truck_uuid(unit, tenant_id)
        if truck_id is None:
            return None

        if suffix == "identity":
            return (await get_truck_identity(db, truck_id, tenant_id)).model_dump(mode="json")
        if suffix == "assignment":
            return (await get_truck_assignment(db, truck_id, tenant_id)).model_dump(mode="json")
        if suffix == "maintenance":
            return (
                await get_truck_maintenance(db, truck_id, include_trend=True, tenant_id=tenant_id)
            ).model_dump(mode="json")
        if suffix == "compliance":
            return (await get_truck_compliance(db, truck_id, tenant_id)).model_dump(mode="json")
        if suffix == "financials":
            return (await get_truck_financials(db, truck_id, tenant_id)).model_dump(mode="json")
        if suffix == "documents":
            return (await get_truck_documents(db, truck_id, tenant_id)).model_dump(mode="json")
    return None


def _compute_delta(old: dict[str, Any] | None, new: dict[str, Any], topic: str) -> dict[str, Any]:
    if old is None:
        return {"refetch": True}
    if any(topic.startswith(p) or topic == p for p in ("recent_documents", "compliance_matrix")):
        return {"refetch": True}
    if topic.startswith("truck_") and topic.endswith(("_maintenance", "_documents")):
        return {"refetch": True}

    delta: dict[str, Any] = {}
    for key, new_val in new.items():
        old_val = old.get(key)
        if old_val != new_val:
            delta[key] = {"old": old_val, "new": new_val}
    if not delta:
        return {}
    return delta


async def push_deltas_for_event(payload: dict[str, Any], tenant_id: int = 1) -> None:
    from app.websocket.topic_mapper import topics_for_document_event

    topics = topics_for_document_event(payload)
    topics = [t for t in topics if t != "document_status"]
    if not topics:
        return

    subscribers = await get_subscribers_for_topics(topics)
    if not subscribers:
        return

    subscribed_set = set()
    for conn_id in subscribers:
        subscribed_set.update(topics)

    for topic in topics:
        if topic not in subscribed_set:
            continue
        new_data = await _fetch_topic_data(topic, tenant_id)
        if new_data is None:
            continue
        old_data = await get_topic_cache(topic)
        delta = _compute_delta(old_data, new_data, topic)
        if not delta:
            await set_topic_cache(topic, new_data)
            continue

        refetch = bool(delta.pop("refetch", False))
        message = build_data_update_message(topic, delta, refetch=refetch or not delta)
        topic_subscribers = await get_subscribers_for_topics([topic])
        if topic_subscribers:
            await ws_manager.broadcast(topic_subscribers, message)
        await set_topic_cache(topic, new_data)
