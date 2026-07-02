#!/usr/bin/env python3
"""Re-queue documents stuck in queued or failed status."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.enums import ProcessingStatus
from app.models.document import Document
from app.redis_client import DOCUMENT_PROCESSING_QUEUE, get_redis
from app.services.document_retry import can_retry, get_pipeline_retry_count
from app.services.queue import enqueue_document_job


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Document).where(
                Document.processing_status.in_(
                    [
                        ProcessingStatus.QUEUED.value,
                        ProcessingStatus.FAILED.value,
                    ]
                )
            )
        )
        docs = list(result.scalars().all())

    to_queue = [doc for doc in docs if can_retry(doc.review_notes)]
    kept = len(docs) - len(to_queue)
    print(
        f"Re-queueing {len(to_queue)} document(s) "
        f"(keeping {kept} at max retries={settings.document_max_retries})"
    )

    async with async_session_factory() as db:
        for doc in to_queue:
            row = await db.get(Document, doc.id)
            if row:
                row.processing_status = ProcessingStatus.QUEUED.value
                row.error_details = None
        await db.commit()

    for doc in to_queue:
        retry_count = get_pipeline_retry_count(doc.review_notes)
        await enqueue_document_job(
            document_id=doc.id,
            file_path=doc.file_path,
            original_filename=doc.original_filename,
            tenant_id=doc.tenant_id,
            retry_count=retry_count,
        )
        print(f"  queued {doc.original_filename} (retry {retry_count})")

    redis = get_redis()
    qlen = await redis.llen(DOCUMENT_PROCESSING_QUEUE)
    print(f"Queue length: {qlen}")


if __name__ == "__main__":
    asyncio.run(main())
