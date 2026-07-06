"""Admin health and learning report API."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends

from app.database import get_db
from app.intelligence.learning.anomaly_calibration import compute_anomaly_calibration
from app.intelligence.learning.document_type_evolution import compute_unknown_document_rate
from app.intelligence.learning.entity_resolution import compute_entity_resolution_stats
from app.intelligence.learning.extraction_accuracy import compute_extraction_accuracy
from app.intelligence.learning.query_satisfaction import compute_query_satisfaction
from app.models.background_job_run import BackgroundJobRun
from app.models.conversation import Conversation, ConversationMessage
from app.models.document import Document
from app.models.system_report import SystemReport
from app.redis_client import DOCUMENT_PROCESSING_QUEUE, get_redis

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/health")
async def admin_health(db: AsyncSession = Depends(get_db)) -> dict:
    extraction = await compute_extraction_accuracy(db)
    entity_res = await compute_entity_resolution_stats(db)
    query_sat = await compute_query_satisfaction(db)
    anomaly_cal = await compute_anomaly_calibration(db)
    doc_evo = await compute_unknown_document_rate(db)

    conv_count = (await db.execute(select(func.count()).select_from(Conversation))).scalar_one() or 0
    msg_count = (await db.execute(select(func.count()).select_from(ConversationMessage))).scalar_one() or 0
    avg_turns = round(msg_count / conv_count, 1) if conv_count else 0.0

    docs_day = (
        await db.execute(
            select(func.count()).select_from(Document).where(Document.processing_status == "complete")
        )
    ).scalar_one() or 0

    jobs = (
        await db.execute(
            select(BackgroundJobRun).order_by(BackgroundJobRun.started_at.desc()).limit(20)
        )
    ).scalars().all()

    redis = await get_redis()
    queue_depth = await redis.llen(DOCUMENT_PROCESSING_QUEUE)

    return {
        "extraction": extraction,
        "entity_resolution": entity_res,
        "conversation_quality": {
            "total_conversations": conv_count,
            "avg_turns_per_conversation": avg_turns,
            "query_satisfaction_rate_pct": query_sat.get("query_satisfaction_rate_pct"),
        },
        "fleet_intelligence": anomaly_cal,
        "document_type_evolution": doc_evo,
        "system_activity": {
            "documents_processed": docs_day,
            "queue_depth": queue_depth,
            "background_job_runs": [
                {
                    "process_name": j.process_name,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                    "entities_processed": j.entities_processed,
                    "anomalies_created": j.anomalies_created,
                    "duration_ms": j.duration_ms,
                }
                for j in jobs
            ],
        },
    }


@router.get("/reports/latest")
async def latest_report(db: AsyncSession = Depends(get_db)) -> dict:
    row = (
        await db.execute(
            select(SystemReport).where(SystemReport.report_type == "weekly_learning").order_by(
                SystemReport.generated_at.desc()
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"report": None}
    return {"report": row.payload, "generated_at": row.generated_at.isoformat()}
