"""Emit intelligence NOTIFY events."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

INTELLIGENCE_NOTIFY_CHANNEL = "intelligence_events"


async def emit_anomalies_updated(db: AsyncSession, count: int, *, tenant_id: int = 1) -> None:
    payload: dict[str, Any] = {
        "type": "anomalies_updated",
        "count": count,
        "tenant_id": tenant_id,
    }
    await db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": INTELLIGENCE_NOTIFY_CHANNEL, "payload": json.dumps(payload)},
    )
