"""Logged background job wrapper."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.schemas import JobRunSummary
from app.models.background_job_run import BackgroundJobRun


async def run_logged_job(
    db: AsyncSession,
    process_name: str,
    fn: Callable[[AsyncSession], Awaitable[JobRunSummary | dict[str, Any]]],
    *,
    tenant_id: int = 1,
) -> JobRunSummary:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    run = BackgroundJobRun(
        tenant_id=tenant_id,
        process_name=process_name,
        started_at=started,
    )
    db.add(run)
    await db.flush()

    summary = JobRunSummary(process_name=process_name, started_at=started)
    try:
        result = await fn(db)
        if isinstance(result, JobRunSummary):
            summary = result
        elif isinstance(result, dict):
            summary.entities_processed = int(result.get("entities_processed", 0))
            summary.anomalies_created = int(result.get("anomalies_created", 0))
            summary.anomalies_updated = int(result.get("anomalies_updated", 0))
            summary.anomalies_resolved = int(result.get("anomalies_resolved", 0))
            summary.details = result.get("details") or {}
    finally:
        finished = datetime.now(timezone.utc)
        summary.finished_at = finished
        summary.duration_ms = int((time.perf_counter() - t0) * 1000)
        run.finished_at = finished
        run.entities_processed = summary.entities_processed
        run.anomalies_created = summary.anomalies_created
        run.anomalies_updated = summary.anomalies_updated
        run.anomalies_resolved = summary.anomalies_resolved
        run.duration_ms = summary.duration_ms
        run.details = summary.details or None
        await db.flush()

    return summary
