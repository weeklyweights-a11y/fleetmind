"""Redis queue consumer with in-process concurrency."""

from __future__ import annotations

import asyncio
import json
import logging
import signal

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.enums import ProcessingStatus
from app.models.document import Document
from app.redis_client import DOCUMENT_PROCESSING_DLQ, DOCUMENT_PROCESSING_QUEUE, close_redis, get_redis
from app.services.document_retry import persist_pipeline_retry_count
from app.worker import processor

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)


async def _mark_failed(document_id: str, error: str, to_dlq: bool = False) -> None:
    async with async_session_factory() as db:
        from uuid import UUID

        result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
        doc = result.scalar_one_or_none()
        if doc:
            doc.processing_status = ProcessingStatus.FAILED.value
            doc.error_details = error
            await db.commit()
    if to_dlq:
        redis = get_redis()
        await redis.lpush(DOCUMENT_PROCESSING_DLQ, json.dumps({"document_id": document_id, "error": error}))


async def _handle_job(job: dict, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        document_id = job.get("document_id")
        file_path = job.get("file_path")
        tenant_id = int(job.get("tenant_id", 1))
        retry_count = int(job.get("retry_count", 0))

        if not document_id or not file_path:
            logger.error("Invalid job payload: %s", job)
            return

        try:
            await asyncio.wait_for(
                processor.process_document(document_id, file_path, tenant_id=tenant_id),
                timeout=settings.document_processing_timeout_sec,
            )
            logger.info("Completed document %s", document_id)
        except asyncio.TimeoutError:
            retry_count += 1
            error = (
                f"Processing timed out after {settings.document_processing_timeout_sec}s"
            )
            logger.error("Job timed out for %s (attempt %s)", document_id, retry_count)
            await persist_pipeline_retry_count(document_id, retry_count)
            if retry_count >= settings.document_max_retries:
                await _mark_failed(
                    document_id,
                    f"Failed after {retry_count} attempts: {error}",
                    to_dlq=True,
                )
            else:
                redis = get_redis()
                job["retry_count"] = retry_count
                await redis.lpush(DOCUMENT_PROCESSING_QUEUE, json.dumps(job))
        except Exception as exc:
            retry_count += 1
            logger.exception("Job failed for %s (attempt %s)", document_id, retry_count)
            await persist_pipeline_retry_count(document_id, retry_count)
            if retry_count >= settings.document_max_retries:
                await _mark_failed(
                    document_id,
                    f"Failed after {retry_count} attempts: {exc}",
                    to_dlq=True,
                )
            else:
                redis = get_redis()
                job["retry_count"] = retry_count
                await redis.lpush(DOCUMENT_PROCESSING_QUEUE, json.dumps(job))


async def consume_jobs(stop_event: asyncio.Event) -> None:
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — image PDF and L6 correction will be limited")

    redis = get_redis()
    semaphore = asyncio.Semaphore(settings.worker_concurrency)
    in_flight: set[asyncio.Task] = set()
    logger.info(
        "Worker started, polling %s (concurrency=%s)",
        DOCUMENT_PROCESSING_QUEUE,
        settings.worker_concurrency,
    )

    while not stop_event.is_set():
        try:
            result = await redis.brpop(DOCUMENT_PROCESSING_QUEUE, timeout=1)
            if result is None:
                in_flight = {t for t in in_flight if not t.done()}
                if not in_flight:
                    await asyncio.sleep(0)
                continue
            _, payload_raw = result
            job = json.loads(payload_raw)
            task = asyncio.create_task(_handle_job(job, semaphore))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Worker error while polling queue")
            await asyncio.sleep(1)

    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)


async def main() -> None:
    stop_event = asyncio.Event()

    def _handle_signal(*_args):
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        await consume_jobs(stop_event)
    finally:
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
