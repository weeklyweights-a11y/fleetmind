"""Daily baseline recompute job."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.anomalies.detectors.runner import run_all_auto_resolvers, run_fleet_detectors
from app.intelligence.baselines.compute import recompute_all
from app.intelligence.job_logging import run_logged_job
from app.intelligence.jobs.compliance_scanner import run_compliance_scan_job
from app.intelligence.schemas import JobRunSummary


async def daily_baseline_recompute(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    entities = await recompute_all(db, tenant_id=tenant_id)
    resolved = await run_all_auto_resolvers(db, tenant_id=tenant_id)
    detection = await run_fleet_detectors(db, tenant_id=tenant_id)
    return {
        "entities_processed": entities,
        "anomalies_created": detection.created,
        "anomalies_resolved": resolved,
        "details": {"skipped": detection.skipped},
    }


async def run_daily_job(db: AsyncSession, *, tenant_id: int = 1) -> JobRunSummary:
    async def _inner(session: AsyncSession) -> JobRunSummary:
        await run_compliance_scan_job(session, tenant_id=tenant_id)
        return await daily_baseline_recompute(session, tenant_id=tenant_id)

    return await run_logged_job(db, "daily_intelligence", _inner, tenant_id=tenant_id)


if __name__ == "__main__":
    import asyncio

    from app.database import async_session_factory

    async def main() -> None:
        async with async_session_factory() as db:
            summary = await run_daily_job(db, tenant_id=1)
            await db.commit()
            print(summary)

    asyncio.run(main())
