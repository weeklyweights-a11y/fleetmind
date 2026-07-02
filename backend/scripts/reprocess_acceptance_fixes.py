#!/usr/bin/env python3
"""Re-queue documents affected by classifier / resolution fixes."""

from __future__ import annotations

import asyncio

from sqlalchemy import delete, select

from app.database import async_session_factory
from app.enums import DocumentType, ProcessingStatus
from app.models.document import Document
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.maintenance_event import MaintenanceEvent
from app.services.queue import enqueue_document_job

IFTA_MISCLASSIFIED = ("document_044.pdf", "document_045.pdf", "document_046.pdf")

TRUCK_DEPENDENT = (
    DocumentType.SERVICE_INVOICE.value,
    DocumentType.INSURANCE_CARD.value,
    DocumentType.IRP_CAB_CARD.value,
    DocumentType.TITLE.value,
    DocumentType.FORM_2290.value,
)


async def main() -> None:
    async with async_session_factory() as db:
        misclassified = (
            await db.execute(
                select(Document).where(Document.original_filename.in_(IFTA_MISCLASSIFIED))
            )
        ).scalars().all()
        silent_failures = (
            await db.execute(
                select(Document).where(
                    Document.document_type.in_(TRUCK_DEPENDENT),
                    Document.truck_id.is_(None),
                )
            )
        ).scalars().all()

    to_queue = {doc.id: doc for doc in (*misclassified, *silent_failures)}
    print(f"Re-queueing {len(to_queue)} document(s)")

    async with async_session_factory() as db:
        if misclassified:
            ifta_ids = [doc.id for doc in misclassified]
            wrong_maint = (
                await db.execute(
                    select(MaintenanceEvent).where(MaintenanceEvent.source_document_id.in_(ifta_ids))
                )
            ).scalars().all()
            for event in wrong_maint:
                await db.delete(event)
            if wrong_maint:
                print(f"  removed {len(wrong_maint)} misclassified maintenance row(s) from IFTA docs")
            await db.execute(
                delete(DocumentNormalizedRecord).where(
                    DocumentNormalizedRecord.document_id.in_(ifta_ids)
                )
            )

        for doc in to_queue.values():
            row = await db.get(Document, doc.id)
            if row:
                row.processing_status = ProcessingStatus.QUEUED.value
                row.error_details = None
        await db.commit()

    for doc in to_queue.values():
        await enqueue_document_job(
            document_id=doc.id,
            file_path=doc.file_path,
            original_filename=doc.original_filename,
            tenant_id=doc.tenant_id,
        )
        print(f"  queued {doc.original_filename}")


if __name__ == "__main__":
    asyncio.run(main())
