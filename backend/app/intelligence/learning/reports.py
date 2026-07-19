"""Weekly learning report assembly."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.learning.extraction_accuracy import compute_extraction_accuracy
from app.intelligence.learning.entity_resolution import compute_entity_resolution_stats
from app.intelligence.learning.anomaly_calibration import compute_anomaly_calibration
from app.intelligence.learning.document_type_evolution import compute_unknown_document_rate
from app.intelligence.learning.query_satisfaction import compute_query_satisfaction
from app.models.system_report import SystemReport


async def run_weekly_learning_report(db: AsyncSession, *, tenant_id: int = 1) -> dict:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extraction": await compute_extraction_accuracy(db, tenant_id=tenant_id),
        "entity_resolution": await compute_entity_resolution_stats(db, tenant_id=tenant_id),
        "query_satisfaction": await compute_query_satisfaction(db, tenant_id=tenant_id),
        "anomaly_calibration": await compute_anomaly_calibration(db, tenant_id=tenant_id),
        "document_type_evolution": await compute_unknown_document_rate(db, tenant_id=tenant_id),
        "recommended_prompt_defaults": "Diagnostic only — review weekly report for prompt tuning suggestions.",
    }
    report = SystemReport(
        tenant_id=tenant_id,
        report_type="weekly_learning",
        generated_at=datetime.now(timezone.utc),
        payload=payload,
    )
    db.add(report)
    await db.flush()
    return {"entities_processed": 1, "details": {"report_id": str(report.id)}}
