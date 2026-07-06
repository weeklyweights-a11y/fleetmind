"""Cross-session memory helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.session import get_active_unresolved_items
from app.models.document import Document
from app.models.maintenance_event import MaintenanceEvent
from app.models.vendor import Vendor


async def get_new_documents_since(
    db: AsyncSession,
    entities_discussed: list[dict[str, Any]] | None,
    ended_at: datetime | None,
    tenant_id: int = 1,
) -> list[dict[str, Any]]:
    if not ended_at or not entities_discussed:
        return []
    truck_ids: list[uuid.UUID] = []
    for ent in entities_discussed:
        if not isinstance(ent, dict):
            continue
        if ent.get("type") == "truck" and ent.get("id"):
            try:
                truck_ids.append(uuid.UUID(str(ent["id"])))
            except ValueError:
                pass
    if not truck_ids:
        return []

    docs = (
        await db.execute(
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.truck_id.in_(truck_ids),
                Document.created_at > ended_at,
            )
            .order_by(Document.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    out: list[dict[str, Any]] = []
    for doc in docs:
        vendor_name = None
        cost = None
        evt = (
            await db.execute(
                select(MaintenanceEvent).where(MaintenanceEvent.source_document_id == doc.id).limit(1)
            )
        ).scalar_one_or_none()
        if evt:
            cost = float(evt.total_cost) if evt.total_cost is not None else None
            if evt.vendor_id:
                vendor_name = (
                    await db.execute(select(Vendor.name).where(Vendor.id == evt.vendor_id))
                ).scalar_one_or_none()
        out.append(
            {
                "document_id": str(doc.id),
                "document_number": doc.document_number,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "vendor_name": vendor_name,
                "cost": cost,
            }
        )
    return out


async def get_tracking_items(db: AsyncSession, operator_name: str, tenant_id: int = 1) -> list[dict[str, Any]]:
    return await get_active_unresolved_items(db, operator_name, tenant_id=tenant_id)
