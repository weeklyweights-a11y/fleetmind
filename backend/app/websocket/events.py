import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.database import async_session_factory

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL = "document_events"


async def notify_document_event(payload: dict[str, Any]) -> None:
    """Emit Postgres NOTIFY for WebSocket fan-out."""
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": NOTIFY_CHANNEL, "payload": json.dumps(payload)},
        )
        await session.commit()


def build_document_status_message(payload: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if payload.get("document_type"):
        details["document_type"] = payload["document_type"]
    if payload.get("truck_unit") is not None:
        details["truck_unit"] = payload["truck_unit"]
    elif payload.get("truck_id"):
        details["truck_id"] = payload["truck_id"]
    for key in ("error_details", "affected_tables", "driver_id", "vendor_id"):
        if payload.get(key) is not None:
            details[key] = payload[key]

    message: dict[str, Any] = {
        "type": "document_status",
        "document_id": payload.get("document_id"),
        "filename": payload.get("filename"),
        "status": payload.get("status"),
    }
    if payload.get("progress"):
        message["progress"] = payload["progress"]
    if details:
        message["details"] = details
    return message


def build_data_update_message(
    topic: str,
    delta: dict[str, Any],
    *,
    refetch: bool = False,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "type": "data_update",
        "topic": topic,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "delta": delta,
    }
    if refetch:
        message["refetch"] = True
    return message
