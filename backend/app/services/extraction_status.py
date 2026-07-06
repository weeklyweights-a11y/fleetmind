"""Extraction status updates and NOTIFY."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
    if status_str == ProcessingStatus.COMPLETE.value and settings.intelligence_enabled:
        from app.intelligence.hooks.document_complete import on_document_complete

        hook_payload = {
            **payload,
            "document_type": doc.document_type,
            "truck_id": str(doc.truck_id) if doc.truck_id else payload.get("truck_id"),
            "vendor_id": str(extra.get("vendor_id")) if extra and extra.get("vendor_id") else None,
        }
        if extra and extra.get("affected_tables"):
            hook_payload["affected_tables"] = extra["affected_tables"]
        import asyncio

        asyncio.create_task(on_document_complete(hook_payload))
