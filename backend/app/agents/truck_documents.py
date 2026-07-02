"""Truck documents sub-agent."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.models.document import Document
from app.schemas.trucks import DocumentTypeGroup, TruckDocumentItem, TruckDocumentsResponse


def _doc_item(doc: Document) -> TruckDocumentItem:
    return TruckDocumentItem(
        document_id=doc.id,
        document_number=doc.document_number,
        document_date=doc.document_date,
        filename=doc.original_filename,
        file_path=doc.file_path,
        status=doc.processing_status,
        confidence=doc.parse_confidence,
    )


async def get_truck_documents(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckDocumentsResponse:
    direct = (
        await db.execute(
            select(Document)
            .where(Document.truck_id == truck_id, Document.tenant_id == tenant_id)
            .order_by(Document.document_date.desc().nullslast(), Document.created_at.desc())
        )
    ).scalars().all()

    driver_ids = (
        await db.execute(
            select(Assignment.driver_id).where(
                Assignment.truck_id == truck_id, Assignment.tenant_id == tenant_id
            )
        )
    ).scalars().all()

    related: list[Document] = []
    if driver_ids:
        related = (
            await db.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.driver_id.in_(driver_ids),
                    Document.truck_id != truck_id,
                )
            )
        ).scalars().all()

    by_type: dict[str, DocumentTypeGroup] = {}
    for doc in direct:
        dtype = doc.document_type or "unknown"
        if dtype not in by_type:
            by_type[dtype] = DocumentTypeGroup(count=0, documents=[])
        by_type[dtype].count += 1
        by_type[dtype].documents.append(_doc_item(doc))

    timeline = [_doc_item(d) for d in direct]
    related_items = [_doc_item(d) for d in related]

    return TruckDocumentsResponse(
        total_documents=len(direct),
        by_type=by_type,
        timeline=timeline,
        related_documents=related_items,
    )
