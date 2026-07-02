"""Extraction status updates and NOTIFY."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ProcessingStatus
from app.models.document import Document
from app.websocket.events import notify_document_event


async def update_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status: ProcessingStatus | str,
    extra: dict[str, Any] | None = None,
) -> None:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one()
    doc.processing_status = str(status)
    payload: dict[str, Any] = {
        "document_id": str(document_id),
        "status": str(status),
        "filename": doc.original_filename,
    }
    if extra:
        payload.update(extra)
    await db.flush()
    await notify_document_event(payload)
