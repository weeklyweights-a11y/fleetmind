"""Run anomaly detectors."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.anomalies.detectors.auto_resolve import run_auto_resolvers
from app.intelligence.anomalies.detectors.cost_spike import detect_cost_spike
from app.intelligence.anomalies.detectors.efficiency_decline import detect_efficiency_decline
from app.intelligence.anomalies.detectors.frequency_unusual import detect_frequency_unusual
from app.intelligence.anomalies.detectors.missing_document import detect_missing_document
from app.intelligence.anomalies.detectors.recurring_issue import detect_recurring_issue
from app.intelligence.anomalies.detectors.unknown_document import detect_unknown_document
from app.intelligence.anomalies.detectors.vendor_cost_increase import detect_vendor_cost_increase
from app.intelligence.anomalies.service import upsert_anomaly
from app.intelligence.schemas import DetectionResult
from app.models.truck import Truck
from app.models.vendor import Vendor


async def _run_candidates(
    db: AsyncSession,
    candidates: list,
    *,
    tenant_id: int = 1,
) -> DetectionResult:
    result = DetectionResult()
    for c in candidates:
        row, created = await upsert_anomaly(db, c, tenant_id=tenant_id)
        if created:
            result.created += 1
        elif row:
            result.updated += 1
        else:
            result.skipped += 1
    return result


async def run_detectors_for_truck(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> DetectionResult:
    combined = DetectionResult()
    detectors = [
        detect_cost_spike,
        detect_frequency_unusual,
        detect_efficiency_decline,
        detect_recurring_issue,
        detect_missing_document,
    ]
    for fn in detectors:
        candidates = await fn(db, truck_id, tenant_id=tenant_id)
        sub = await _run_candidates(db, candidates, tenant_id=tenant_id)
        combined.created += sub.created
        combined.updated += sub.updated
        combined.skipped += sub.skipped
    return combined


async def run_vendor_detectors(
    db: AsyncSession,
    vendor_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> DetectionResult:
    candidates = await detect_vendor_cost_increase(db, vendor_id, tenant_id=tenant_id)
    return await _run_candidates(db, candidates, tenant_id=tenant_id)


async def run_fleet_detectors(db: AsyncSession, *, tenant_id: int = 1) -> DetectionResult:
    combined = DetectionResult()
    candidates = await detect_unknown_document(db, tenant_id=tenant_id)
    sub = await _run_candidates(db, candidates, tenant_id=tenant_id)
    combined.created += sub.created
    combined.skipped += sub.skipped

    trucks = (await db.execute(select(Truck.id).where(Truck.tenant_id == tenant_id))).scalars().all()
    for tid in trucks:
        sub = await run_detectors_for_truck(db, tid, tenant_id=tenant_id)
        combined.created += sub.created
        combined.skipped += sub.skipped

    vendors = (await db.execute(select(Vendor.id).where(Vendor.tenant_id == tenant_id))).scalars().all()
    for vid in vendors:
        sub = await run_vendor_detectors(db, vid, tenant_id=tenant_id)
        combined.created += sub.created
        combined.skipped += sub.skipped

    return combined


async def run_all_auto_resolvers(db: AsyncSession, *, tenant_id: int = 1) -> int:
    return await run_auto_resolvers(db, tenant_id=tenant_id)
