#!/usr/bin/env python3
"""Re-queue failed and needs_review documents for reprocessing."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.enums import ProcessingStatus
from app.models.document import Document
from app.redis_client import DOCUMENT_PROCESSING_QUEUE, get_redis
from app.services.document_retry import can_retry, get_pipeline_retry_count, set_pipeline_retry_count
from app.services.queue import enqueue_document_job


async def main() -> None:
    statuses = [
        ProcessingStatus.QUEUED.value,
        ProcessingStatus.FAILED.value,
        ProcessingStatus.NEEDS_REVIEW.value,
    ]
    async with async_session_factory() as db:
        result = await db.execute(select(Document).where(Document.processing_status.in_(statuses)))
        docs = list(result.scalars().all())

    to_queue: list[Document] = []
    kept = 0
    for doc in docs:
        if doc.processing_status == ProcessingStatus.FAILED.value and not can_retry(doc.review_notes):
            kept += 1
            continue
        to_queue.append(doc)

    print(
        f"Re-queueing {len(to_queue)} document(s) "
        f"(keeping {kept} at max retries={settings.document_max_retries})"
    )
    async with async_session_factory() as db:
        for doc in to_queue:
            row = await db.get(Document, doc.id)
            if not row:
                continue
            retry_count = get_pipeline_retry_count(row.review_notes)
            was_failed = row.processing_status == ProcessingStatus.FAILED.value
            if was_failed:
                retry_count += 1
                row.review_notes = set_pipeline_retry_count(row.review_notes, retry_count)
                row.error_details = (
                    f"Retry {retry_count}/{settings.document_max_retries}: reprocess"
                )
            else:
                row.error_details = None
            row.processing_status = ProcessingStatus.QUEUED.value
        await db.commit()

    for doc in to_queue:
        async with async_session_factory() as db:
            row = await db.get(Document, doc.id)
            retry_count = get_pipeline_retry_count(row.review_notes) if row else 0
        await enqueue_document_job(
            document_id=doc.id,
            file_path=doc.file_path,
            original_filename=doc.original_filename,
            tenant_id=doc.tenant_id,
            retry_count=retry_count,
        )
        print(f"  queued {doc.original_filename} (retry {retry_count})")

    redis = get_redis()
    print(f"Queue length: {await redis.llen(DOCUMENT_PROCESSING_QUEUE)}")


if __name__ == "__main__":
    asyncio.run(main())
