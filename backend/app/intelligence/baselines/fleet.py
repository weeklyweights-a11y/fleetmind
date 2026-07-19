"""Fleet-level baseline metrics."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import compliance_snapshot_counts
from app.intelligence.baselines.stats import mom_change_pct, monthly_buckets, qoq_change_pct
from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.document import Document
from app.models.maintenance_event import MaintenanceEvent
from app.models.truck import Truck


async def compute_fleet_baselines(
    db: AsyncSession,
    *,
    tenant_id: int = 1,
) -> int:
    today = date.today()
    period_start = today.replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    written = 0

    truck_count = (
        await db.execute(
            select(func.count()).select_from(Truck).where(Truck.tenant_id == tenant_id, Truck.status == "active")
        )
    ).scalar_one() or 0

    events = (
        await db.execute(
            select(MaintenanceEvent).where(MaintenanceEvent.tenant_id == tenant_id)
        )
    ).scalars().all()

    total_spend = sum((e.total_cost for e in events), Decimal("0"))
    spend_buckets = monthly_buckets([(e.service_date, e.total_cost) for e in events])
    monthly_totals = [sum(v) for k, v in sorted(spend_buckets.items())]

    if truck_count:
        avg_per_truck = float(total_spend) / truck_count / max(len(monthly_totals), 1)
        await upsert_fleet_metric(
            db,
            entity_type="fleet",
            entity_id=None,
            metric_name="fleet_avg_maintenance_per_truck_month",
            value=Decimal(str(round(avg_per_truck, 4))),
            period_type="monthly",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 1

    if events:
        avg_event = float(total_spend / len(events))
        await upsert_fleet_metric(
            db,
            entity_type="fleet",
            entity_id=None,
            metric_name="fleet_avg_cost_per_event",
            value=Decimal(str(round(avg_event, 4))),
            period_type="all_time",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 1

    if monthly_totals:
        await upsert_fleet_metric(
            db,
            entity_type="fleet",
            entity_id=None,
            metric_name="fleet_maintenance_spend_mom_change_pct",
            value=Decimal(str(round(mom_change_pct(monthly_totals), 4))),
            period_type="monthly",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        await upsert_fleet_metric(
            db,
            entity_type="fleet",
            entity_id=None,
            metric_name="fleet_maintenance_spend_qoq_change_pct",
            value=Decimal(str(round(qoq_change_pct(monthly_totals), 4))),
            period_type="monthly",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 2

    fully, warnings, expirations, incomplete, _ = await compliance_snapshot_counts(db, tenant_id)
    total_trucks = fully + warnings + expirations + incomplete
    score = (fully / total_trucks * 100) if total_trucks else 0.0
    await upsert_fleet_metric(
        db,
        entity_type="fleet",
        entity_id=None,
        metric_name="compliance_health_score",
        value=Decimal(str(round(score, 4))),
        period_type="monthly",
        period_start=period_start,
        period_end=period_end,
        tenant_id=tenant_id,
    )
    written += 1

    # Docs per week
    week_ago = today - timedelta(days=7)
    docs_week = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.processing_status == "complete",
                Document.created_at >= week_ago,
            )
        )
    ).scalar_one() or 0
    await upsert_fleet_metric(
        db,
        entity_type="fleet",
        entity_id=None,
        metric_name="document_processing_rate",
        value=Decimal(str(docs_week)),
        period_type="weekly",
        period_start=week_ago,
        period_end=today,
        tenant_id=tenant_id,
    )
    written += 1

    return written
