"""APScheduler background jobs in worker."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import async_session_factory
from app.intelligence.job_logging import run_logged_job
from app.intelligence.jobs.compliance_scanner import run_compliance_scan_job
from app.intelligence.jobs.daily_baseline_recompute import daily_baseline_recompute
from app.intelligence.jobs.unresolved_checker import run_unresolved_checker
from app.intelligence.learning.reports import run_weekly_learning_report

logger = logging.getLogger(__name__)


async def _run_logged(process_name: str, fn) -> None:
    async with async_session_factory() as db:
        try:
            await run_logged_job(db, process_name, fn)
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def _job_compliance_scan() -> None:
    if not settings.intelligence_enabled:
        return
    await _run_logged("compliance_scan", run_compliance_scan_job)


async def _job_daily_baseline() -> None:
    if not settings.intelligence_enabled:
        return
    await _run_logged("daily_baseline_recompute", daily_baseline_recompute)


async def _job_unresolved_checker() -> None:
    if not settings.intelligence_enabled:
        return
    await _run_logged("unresolved_checker", run_unresolved_checker)


async def _job_weekly_report() -> None:
    if not settings.intelligence_enabled:
        return
    await _run_logged("weekly_learning_report", run_weekly_learning_report)


async def start_scheduler(stop_event: asyncio.Event) -> None:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _job_compliance_scan,
        CronTrigger(hour=settings.compliance_scan_hour, minute=0),
        id="compliance_scan",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_daily_baseline,
        CronTrigger(hour=settings.baseline_recompute_hour, minute=0),
        id="daily_baseline",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_unresolved_checker,
        IntervalTrigger(hours=settings.unresolved_check_interval_hours),
        id="unresolved_checker",
        replace_existing=True,
    )
    scheduler.add_job(
        _job_weekly_report,
        CronTrigger(day_of_week=settings.weekly_report_dow, hour=0, minute=0),
        id="weekly_learning_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Intelligence scheduler started")
    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Intelligence scheduler stopped")
