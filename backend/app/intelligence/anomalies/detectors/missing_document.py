"""Missing document detection."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.schemas import AnomalyCandidate
from app.models.document import Document
from app.models.truck import Truck


async def detect_missing_document(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> list[AnomalyCandidate]:
    truck = (await db.execute(select(Truck).where(Truck.id == truck_id))).scalar_one_or_none()
    if not truck:
        return []

    doc_count = (
        await db.execute(
            select(func.count()).select_from(Document).where(
                Document.truck_id == truck_id, Document.tenant_id == tenant_id,
            )
        )
    ).scalar_one() or 0

    trucks_with_docs = (
        await db.execute(
            select(Document.truck_id, func.count().label("cnt"))
            .where(Document.tenant_id == tenant_id, Document.truck_id.isnot(None))
            .group_by(Document.truck_id)
        )
    ).all()
    if trucks_with_docs:
        fleet_avg = sum(r.cnt for r in trucks_with_docs) / len(trucks_with_docs)
    else:
        fleet_avg = 0.0
    age_years = 1
    if truck.acquired_date:
        age_years = max((date.today() - truck.acquired_date).days / 365, 0.5)

    expected = fleet_avg * min(age_years, 3) / 3
    if doc_count >= expected * 0.5 or expected < 2:
        return []

    return [
        AnomalyCandidate(
            anomaly_type="missing_document",
            entity_type="truck",
            entity_id=truck_id,
            description=(
                f"Truck {truck.unit_number} has {doc_count} documents on file, "
                f"below fleet average for its age."
            ),
            severity="info",
            supporting_data={
                "metric": "document_count",
                "current_value": doc_count,
                "baseline_mean": expected,
            },
        )
    ]
