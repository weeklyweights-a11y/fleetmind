"""Pipeline retry tracking and stuck-document handling."""

from __future__ import annotations

import re
from uuid import UUID

from app.config import settings
from app.database import async_session_factory
from app.enums import ProcessingStatus
from app.models.document import Document
from app.services.queue import enqueue_document_job

_RETRY_RE = re.compile(r"\[pipeline_retry=(\d+)\]")

TERMINAL_STATUSES = frozenset(
    {
        ProcessingStatus.COMPLETE.value,
        ProcessingStatus.FAILED.value,
        ProcessingStatus.NEEDS_REVIEW.value,
    }
)

IN_FLIGHT_STATUSES = frozenset(
    {
        ProcessingStatus.QUEUED.value,
        ProcessingStatus.PARSING.value,
        ProcessingStatus.EXTRACTING.value,
        ProcessingStatus.NORMALIZING.value,
        ProcessingStatus.VALIDATING.value,
    }
)


def get_pipeline_retry_count(review_notes: str | None) -> int:
    if not review_notes:
        return 0
    match = _RETRY_RE.search(review_notes)
    return int(match.group(1)) if match else 0


def set_pipeline_retry_count(review_notes: str | None, count: int) -> str:
    base = _RETRY_RE.sub("", review_notes or "").strip()
    tag = f"[pipeline_retry={count}]"
    return f"{tag} {base}".strip() if base else tag


def can_retry(review_notes: str | None) -> bool:
    return get_pipeline_retry_count(review_notes) < settings.document_max_retries


async def persist_pipeline_retry_count(document_id: str, count: int) -> None:
    async with async_session_factory() as db:
        doc = await db.get(Document, UUID(document_id))
        if doc:
            doc.review_notes = set_pipeline_retry_count(doc.review_notes, count)
            await db.commit()


async def mark_max_retries_exceeded(document_id: str, reason: str) -> None:
    async with async_session_factory() as db:
        doc = await db.get(Document, UUID(document_id))
        if not doc:
            return
        count = get_pipeline_retry_count(doc.review_notes)
        doc.processing_status = ProcessingStatus.FAILED.value
        doc.error_details = (
            f"Max retries ({settings.document_max_retries}) exceeded: {reason}"
        )
        doc.review_notes = set_pipeline_retry_count(doc.review_notes, count)
        await db.commit()


async def skip_stuck_and_requeue(document_id: str, reason: str) -> None:
    """Re-queue a stuck document or mark failed after max retries."""
    async with async_session_factory() as db:
        doc = await db.get(Document, UUID(document_id))
        if not doc:
            return
        current = get_pipeline_retry_count(doc.review_notes)
        if current >= settings.document_max_retries:
            doc.processing_status = ProcessingStatus.FAILED.value
            doc.error_details = (
                f"Max retries ({settings.document_max_retries}) exceeded: {reason}"
            )
            await db.commit()
            return

        new_count = current + 1
        doc.review_notes = set_pipeline_retry_count(doc.review_notes, new_count)
        doc.processing_status = ProcessingStatus.QUEUED.value
        doc.error_details = f"Retry {new_count}/{settings.document_max_retries}: {reason}"
        tenant_id = doc.tenant_id
        file_path = doc.file_path
        filename = doc.original_filename
        await db.commit()

    await enqueue_document_job(
        document_id=UUID(document_id),
        file_path=file_path,
        original_filename=filename,
        tenant_id=tenant_id,
        retry_count=new_count,
    )
