import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL = "document_events"


async def notify_document_event(payload: dict[str, Any]) -> None:
    """Stub helper for Phase 2 worker to emit Postgres NOTIFY events."""
    async with async_session_factory() as session:
        await session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": NOTIFY_CHANNEL, "payload": json.dumps(payload)},
        )
        await session.commit()


def build_document_status_message(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "document_status",
        "document_id": payload.get("document_id"),
        "status": payload.get("status"),
        "details": {
            k: v
            for k, v in payload.items()
            if k not in {"document_id", "status"}
        },
    }


def build_data_update_message(entity_type: str, entity_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "data_update",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "changes": changes,
    }
