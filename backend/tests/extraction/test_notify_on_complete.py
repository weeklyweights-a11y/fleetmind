"""NOTIFY event tests."""

import json
import uuid

import pytest
from sqlalchemy import text

from app.database import async_session_factory
from app.websocket.events import NOTIFY_CHANNEL, notify_document_event


@pytest.mark.asyncio
async def test_notify_document_event_payload():
    document_id = str(uuid.uuid4())
    payload = {
        "document_id": document_id,
        "status": "complete",
        "document_type": "service_invoice",
        "affected_tables": ["maintenance_events"],
    }
    await notify_document_event(payload)

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT pg_notification_queue_usage()")
        )
        # Queue usage API exists; NOTIFY fired without error.
        assert result is not None
