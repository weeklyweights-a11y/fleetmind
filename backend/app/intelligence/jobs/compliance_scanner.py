"""Compliance gap scanning and cache."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import build_truck_compliance_categories
from app.intelligence.anomalies.service import auto_resolve_matching, upsert_anomaly
from app.intelligence.config import THRESHOLDS
from app.intelligence.schemas import AnomalyCandidate
from app.models.truck import Truck
from app.redis_client import get_redis

CACHE_TTL_SECONDS = 25 * 3600
CACHE_KEY_PREFIX = "compliance_scan"


@dataclass
class ComplianceScanItem:
    truck_id: uuid.UUID
    unit_number: int
    compliance_type: str
    days_remaining: int | None
    expiry_date: str | None
    missing: bool
    severity: str | None


def _severity_for_days(days: int | None, missing: bool) -> str | None:
    if missing:
        return "warning"
    if days is None:
        return None
    if days > THRESHOLDS.compliance_info_days_max:
        return None
    if days >= THRESHOLDS.compliance_info_days_min:
        return "info"
    if days >= THRESHOLDS.compliance_warning_days_min:
        return "warning"
    return "critical"


async def scan_compliance_deadlines(
    db: AsyncSession,
    *,
    tenant_id: int = 1,
    truck_id: uuid.UUID | None = None,
) -> list[ComplianceScanItem]:
    items: list[ComplianceScanItem] = []
    query = select(Truck).where(Truck.tenant_id == tenant_id, Truck.status == "active")
    if truck_id:
        query = query.where(Truck.id == truck_id)
    trucks = (await db.execute(query)).scalars().all()

    for truck in trucks:
        cats = await build_truck_compliance_categories(db, truck.id, tenant_id)
        checks = [
            ("insurance", cats.insurance),
            ("registration", cats.registration),
            ("title", cats.title),
            ("emission", cats.emission),
            ("driver_cdl", cats.driver_cdl),
            ("medical_cert", cats.medical_cert),
        ]
        for ctype, detail in checks:
            days = detail.days_remaining
            missing = detail.status == "grey"
            if not missing and days is not None and days > THRESHOLDS.compliance_scan_window_days:
                continue
            if not missing and days is not None and days > 60:
                continue
            severity = _severity_for_days(days, missing)
            if severity is None and not missing:
                continue
            items.append(
                ComplianceScanItem(
                    truck_id=truck.id,
                    unit_number=truck.unit_number,
                    compliance_type=ctype,
                    days_remaining=days,
                    expiry_date=detail.expiry_date,
                    missing=missing,
                    severity=severity or "warning",
                )
            )
    return items


def _to_urgent_items(scan_items: list[ComplianceScanItem]) -> list[dict]:
    urgent = [i for i in scan_items if i.days_remaining is not None and i.days_remaining <= 7]
    urgent.sort(key=lambda x: (x.days_remaining if x.days_remaining is not None else 999))
    return [
        {
            "truck_unit": i.unit_number,
            "compliance_type": i.compliance_type,
            "days_remaining": i.days_remaining,
            "expiry_date": i.expiry_date,
        }
        for i in urgent[:10]
    ]


async def write_compliance_cache(
    db: AsyncSession,
    scan_items: list[ComplianceScanItem],
    *,
    tenant_id: int = 1,
) -> None:
    redis = await get_redis()
    payload = {
        "items": [
            {
                "truck_id": str(i.truck_id),
                "unit_number": i.unit_number,
                "compliance_type": i.compliance_type,
                "days_remaining": i.days_remaining,
                "expiry_date": i.expiry_date,
                "missing": i.missing,
                "severity": i.severity,
            }
            for i in scan_items
        ],
        "urgent_items": _to_urgent_items(scan_items),
    }
    await redis.setex(f"{CACHE_KEY_PREFIX}:{tenant_id}", CACHE_TTL_SECONDS, json.dumps(payload))


async def read_compliance_cache(*, tenant_id: int = 1) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(f"{CACHE_KEY_PREFIX}:{tenant_id}")
    if not raw:
        return None
    return json.loads(raw)


async def run_compliance_scan_job(db: AsyncSession, *, tenant_id: int = 1) -> dict[str, int]:
    items = await scan_compliance_deadlines(db, tenant_id=tenant_id)
    await write_compliance_cache(db, items, tenant_id=tenant_id)
    created = 0
    for item in items:
        if item.missing:
            desc = f"No {item.compliance_type.replace('_', ' ')} record on file for truck {item.unit_number}."
        elif item.days_remaining is not None and item.days_remaining < 0:
            desc = f"EXPIRED — truck {item.unit_number} {item.compliance_type} may not legally operate."
        else:
            desc = (
                f"Truck {item.unit_number} {item.compliance_type} expires in "
                f"{item.days_remaining} days ({item.expiry_date})."
            )
        candidate = AnomalyCandidate(
            anomaly_type="compliance_gap",
            entity_type="truck",
            entity_id=item.truck_id,
            description=desc,
            severity=item.severity or "warning",
            supporting_data={
                "compliance_type": item.compliance_type,
                "days_remaining": item.days_remaining,
                "expiry_date": item.expiry_date,
                "missing": item.missing,
            },
            dedup_key=f"compliance_gap:truck:{item.truck_id}:{item.compliance_type}",
        )
        _, was_created = await upsert_anomaly(db, candidate, tenant_id=tenant_id)
        if was_created:
            created += 1
    return {"entities_processed": len(items), "anomalies_created": created}


async def auto_resolve_compliance_for_truck(
    db: AsyncSession,
    truck_id: uuid.UUID,
    compliance_type: str,
    *,
    tenant_id: int = 1,
) -> int:
    return await auto_resolve_matching(
        db,
        anomaly_type="compliance_gap",
        entity_type="truck",
        entity_id=truck_id,
        compliance_type=compliance_type,
        note=f"Resolved: new {compliance_type} document processed.",
        tenant_id=tenant_id,
    )
