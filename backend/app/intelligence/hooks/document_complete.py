"""Post-ingest intelligence hook."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.config import settings
from app.database import async_session_factory
from app.intelligence.anomalies.detectors.runner import run_detectors_for_truck, run_vendor_detectors
from app.intelligence.anomalies.notify import emit_anomalies_updated
from app.intelligence.baselines.compute import recompute_fleet, recompute_truck, recompute_vendor
from app.intelligence.jobs.compliance_scanner import (
    auto_resolve_compliance_for_truck,
    run_compliance_scan_job,
    scan_compliance_deadlines,
    write_compliance_cache,
)
from app.intelligence.jobs.unresolved_checker import run_unresolved_checker

logger = logging.getLogger(__name__)

_recent: dict[str, float] = {}
_DEDUP_SECONDS = 60


def _should_skip(document_id: str) -> bool:
    now = time.monotonic()
    last = _recent.get(document_id)
    if last and now - last < _DEDUP_SECONDS:
        return True
    _recent[document_id] = now
    return False


async def on_document_complete(payload: dict[str, Any]) -> None:
    if not settings.intelligence_enabled:
        return
    doc_id = str(payload.get("document_id", ""))
    if doc_id and _should_skip(doc_id):
        return

    truck_id_raw = payload.get("truck_id")
    vendor_id_raw = payload.get("vendor_id")
    document_type = payload.get("document_type") or ""
    status = payload.get("status", "")

    if status not in ("complete", ""):
        return

    async with async_session_factory() as db:
        try:
            created = 0
            if truck_id_raw:
                truck_id = uuid.UUID(str(truck_id_raw))
                await recompute_truck(db, truck_id)
                await recompute_fleet(db)
                det = await run_detectors_for_truck(db, truck_id)
                created += det.created
                await run_unresolved_checker(db, truck_id=truck_id)

                if document_type in ("insurance_card", "registration", "title", "emission_cert", "cdl"):
                    ctype_map = {
                        "insurance_card": "insurance",
                        "registration": "registration",
                        "title": "title",
                        "emission_cert": "emission",
                        "cdl": "driver_cdl",
                    }
                    await auto_resolve_compliance_for_truck(
                        db, truck_id, ctype_map.get(document_type, document_type)
                    )
                items = await scan_compliance_deadlines(db, truck_id=truck_id)
                await write_compliance_cache(db, items)

            if vendor_id_raw:
                vendor_id = uuid.UUID(str(vendor_id_raw))
                await recompute_vendor(db, vendor_id)
                vdet = await run_vendor_detectors(db, vendor_id)
                created += vdet.created

            await emit_anomalies_updated(db, created)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("Intelligence hook failed for document %s", doc_id)
