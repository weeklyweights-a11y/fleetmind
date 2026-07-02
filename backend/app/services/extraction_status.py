"""Extraction status updates and NOTIFY."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ProcessingStatus
from app.models.document import Document
from app.services.pipeline_progress import progress_payload
from app.services.truck_unit_lookup import resolve_truck_unit
from app.websocket.events import notify_document_event


async def update_status(
    db: AsyncSession,
    document_id: uuid.UUID,
    status: ProcessingStatus | str,
    extra: dict[str, Any] | None = None,
    *,
    layer_status: str | None = None,
) -> None:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one()
    doc.processing_status = str(status)
    status_str = str(status)
    progress_status = layer_status or status_str
    payload: dict[str, Any] = {
        "document_id": str(document_id),
        "status": status_str,
        "filename": doc.original_filename,
        "progress": progress_payload(progress_status),
    }
    if extra:
        payload.update(extra)
    truck_id = extra.get("truck_id") if extra else None
    if truck_id is None and doc.truck_id:
        truck_id = str(doc.truck_id)
    truck_unit = await resolve_truck_unit(db, truck_id)
    if truck_unit is not None:
        payload["truck_unit"] = truck_unit
    await db.flush()
    await notify_document_event(payload)
