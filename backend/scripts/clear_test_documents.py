#!/usr/bin/env python3
"""Remove test uploads and reset queues before bulk import."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session_factory
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.extraction_correction import ExtractionCorrection
from app.redis_client import DOCUMENT_PROCESSING_DLQ, DOCUMENT_PROCESSING_QUEUE, get_redis


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Document).where(Document.original_filename == "test.pdf")
        )
        docs = result.scalars().all()
        doc_ids = [d.id for d in docs]
        print(f"Found {len(docs)} test.pdf document(s)")

        if doc_ids:
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id.in_(doc_ids))
            )
            await db.execute(
                delete(DocumentNormalizedRecord).where(
                    DocumentNormalizedRecord.document_id.in_(doc_ids)
                )
            )
            await db.execute(
                delete(ExtractionCorrection).where(
                    ExtractionCorrection.document_id.in_(doc_ids)
                )
            )
            await db.execute(delete(Document).where(Document.id.in_(doc_ids)))
            await db.commit()

            storage = Path(settings.document_storage_path)
            for doc in docs:
                path = Path(doc.file_path)
                if path.exists():
                    path.unlink()
                    print(f"  deleted file {path.name}")
                alt = storage / f"{doc.id}.pdf"
                if alt.exists():
                    alt.unlink()
                    print(f"  deleted file {alt.name}")

    redis = get_redis()
    await redis.delete(DOCUMENT_PROCESSING_QUEUE)
    await redis.delete(DOCUMENT_PROCESSING_DLQ)
    print("Cleared Redis processing queues")

    remaining = 0
    async with async_session_factory() as db:
        remaining = len(
            (await db.execute(select(Document))).scalars().all()
        )
    print(f"Documents remaining in database: {remaining}")


if __name__ == "__main__":
    asyncio.run(main())
