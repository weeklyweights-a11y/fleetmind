"""Wait for document processing with stuck detection and skip-forward."""

from __future__ import annotations

import asyncio
import time

import httpx
from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_factory
from app.enums import ProcessingStatus
from app.models.document import Document
from app.services.document_retry import (
    IN_FLIGHT_STATUSES,
    TERMINAL_STATUSES,
    get_pipeline_retry_count,
    mark_max_retries_exceeded,
    skip_stuck_and_requeue,
)


async def count_status() -> dict[str, int]:
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Document.processing_status, func.count()).group_by(
                    Document.processing_status
                )
            )
        ).all()
    return dict(rows)


async def wait_for_documents(
    doc_ids: list[str],
    label: str,
    *,
    api_url: str = "http://api:8000",
    poll_interval_sec: float = 3,
    max_wait_sec: int | None = None,
) -> list[str]:
    """Wait for documents to finish. Skips stuck docs (re-queue up to max retries)."""
    if not doc_ids:
        return []

    pending = set(doc_ids)
    skipped: list[str] = []
    status_since: dict[str, tuple[str, float]] = {}
    deadline = time.time() + (max_wait_sec or settings.document_pipeline_max_wait_sec)
    stuck_timeout = settings.document_stuck_timeout_sec

    print(f"Waiting for {label} ({len(pending)} documents)...", flush=True)

    async with httpx.AsyncClient(timeout=60.0) as client:
        while pending and time.time() < deadline:
            now = time.time()
            for doc_id in list(pending):
                resp = await client.get(f"{api_url}/api/documents/{doc_id}")
                resp.raise_for_status()
                status = resp.json().get("processing_status")

                if status in TERMINAL_STATUSES:
                    pending.discard(doc_id)
                    status_since.pop(doc_id, None)
                    continue

                prev = status_since.get(doc_id)
                if prev is None or prev[0] != status:
                    status_since[doc_id] = (status, now)
                elif status in IN_FLIGHT_STATUSES and now - prev[1] >= stuck_timeout:
                    print(
                        f"  SKIP stuck {doc_id} ({status} for {int(now - prev[1])}s) — "
                        f"retry or mark failed",
                        flush=True,
                    )
                    await skip_stuck_and_requeue(
                        doc_id, f"stuck in {status} for {int(now - prev[1])}s"
                    )
                    pending.discard(doc_id)
                    status_since.pop(doc_id, None)
                    skipped.append(doc_id)

            if pending:
                counts = await count_status()
                print(
                    f"  {label}: {len(pending)} remaining | "
                    f"complete={counts.get('complete', 0)} "
                    f"review={counts.get('needs_review', 0)} "
                    f"failed={counts.get('failed', 0)} "
                    f"queued={counts.get('queued', 0)}",
                    flush=True,
                )
                await asyncio.sleep(poll_interval_sec)

    for doc_id in list(pending):
        print(f"  SKIP timed-out {doc_id} — retry or mark failed", flush=True)
        await skip_stuck_and_requeue(doc_id, f"timed out waiting in {label}")
        skipped.append(doc_id)

    pending.clear()
    return skipped


async def wait_for_worker_idle(
    *,
    poll_interval_sec: float = 3,
    max_wait_sec: int | None = None,
) -> list[str]:
    """Wait until no in-flight documents, skipping any that stay stuck."""
    skipped: list[str] = []
    deadline = time.time() + (max_wait_sec or settings.document_pipeline_max_wait_sec)
    stuck_since: dict[str, float] = {}
    stuck_timeout = settings.document_stuck_timeout_sec

    while time.time() < deadline:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(Document).where(
                        Document.processing_status.in_(tuple(IN_FLIGHT_STATUSES))
                    )
                )
            ).scalars().all()

        now = time.time()
        active_ids = {str(doc.id) for doc in rows}

        for doc_id in list(stuck_since):
            if doc_id not in active_ids:
                stuck_since.pop(doc_id, None)

        for doc in rows:
            doc_id = str(doc.id)
            if doc_id not in stuck_since:
                stuck_since[doc_id] = now
                continue
            if now - stuck_since[doc_id] < stuck_timeout:
                continue
            if get_pipeline_retry_count(doc.review_notes) >= settings.document_max_retries:
                await mark_max_retries_exceeded(
                    doc_id,
                    f"stuck in {doc.processing_status} for {int(now - stuck_since[doc_id])}s",
                )
            else:
                await skip_stuck_and_requeue(
                    doc_id,
                    f"stuck in {doc.processing_status} for {int(now - stuck_since[doc_id])}s",
                )
            skipped.append(doc_id)
            stuck_since.pop(doc_id, None)

        if not rows:
            return skipped

        counts = await count_status()
        in_flight = sum(counts.get(s, 0) for s in IN_FLIGHT_STATUSES)
        print(f"  Waiting for worker: in_flight={in_flight} counts={counts}", flush=True)
        await asyncio.sleep(poll_interval_sec)

    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Document).where(
                    Document.processing_status.in_(tuple(IN_FLIGHT_STATUSES))
                )
            )
        ).scalars().all()
    for doc in rows:
        doc_id = str(doc.id)
        await skip_stuck_and_requeue(doc_id, "pipeline max wait exceeded")
        skipped.append(doc_id)

    return skipped
