"""Per-truck baseline metrics."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.baselines.stats import mean, monthly_buckets, monthly_spend_stats
from app.intelligence.metrics_store import upsert_fleet_metric
from app.models.maintenance_event import MaintenanceEvent
from app.models.mileage_record import MileageRecord


async def compute_truck_baselines(
    db: AsyncSession,
    truck_id: uuid.UUID,
    *,
    tenant_id: int = 1,
) -> int:
    today = date.today()
    period_start = today.replace(day=1)
    period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    written = 0

    events = (
        await db.execute(
            select(MaintenanceEvent)
            .where(MaintenanceEvent.truck_id == truck_id, MaintenanceEvent.tenant_id == tenant_id)
            .order_by(MaintenanceEvent.service_date)
        )
    ).scalars().all()

    spend_buckets = monthly_buckets([(e.service_date, e.total_cost) for e in events])
    count_buckets = monthly_buckets([(e.service_date, 1) for e in events])
    monthly_totals = [sum(v) for k, v in sorted(spend_buckets.items())]
    monthly_counts = [len(v) for k, v in sorted(count_buckets.items())]

    stats = monthly_spend_stats(monthly_totals)
    count_stats = monthly_spend_stats([float(c) for c in monthly_counts]) if monthly_counts else monthly_spend_stats([])

    metric_pairs = [
        ("maintenance_monthly_spend_mean", stats["mean"]),
        ("maintenance_monthly_spend_sd", stats["sd"]),
        ("maintenance_monthly_spend_count", stats["count"]),
        ("maintenance_monthly_spend_min", stats["min"]),
        ("maintenance_monthly_spend_max", stats["max"]),
        ("maintenance_monthly_spend_trend", stats["trend"]),
        ("maintenance_monthly_spend_latest", stats["latest"]),
        ("maintenance_monthly_event_count_mean", count_stats["mean"]),
        ("maintenance_monthly_event_count_sd", count_stats["sd"]),
    ]
    if events:
        total = sum(e.total_cost for e in events)
        metric_pairs.append(("maintenance_avg_cost_per_event", float(total / len(events))))

    for name, val in metric_pairs:
        await upsert_fleet_metric(
            db,
            entity_type="truck",
            entity_id=truck_id,
            metric_name=name,
            value=Decimal(str(round(val, 4))),
            period_type="monthly",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 1

    # Category distribution
    cat_spend: dict[str, Decimal] = {}
    cat_count: dict[str, int] = {}
    total_spend = sum((e.total_cost for e in events), Decimal("0"))
    for e in events:
        cat_spend[e.category] = cat_spend.get(e.category, Decimal("0")) + e.total_cost
        cat_count[e.category] = cat_count.get(e.category, 0) + 1

    months_active = max(len(spend_buckets), 1)
    for cat, spend in cat_spend.items():
        safe_cat = cat.replace(" ", "_").lower()
        pct = float(spend / total_spend * 100) if total_spend else 0.0
        events_per_year = cat_count[cat] / months_active * 12
        for name, val in [
            (f"maintenance_category_{safe_cat}_spend_pct", pct),
            (f"maintenance_category_{safe_cat}_event_count", float(cat_count[cat])),
            (f"maintenance_category_{safe_cat}_events_per_year", events_per_year),
        ]:
            await upsert_fleet_metric(
                db,
                entity_type="truck",
                entity_id=truck_id,
                metric_name=name,
                value=Decimal(str(round(val, 4))),
                period_type="all_time",
                period_start=period_start,
                period_end=period_end,
                tenant_id=tenant_id,
            )
            written += 1

    # Odometer / cost per mile
    mileage = (
        await db.execute(
            select(MileageRecord)
            .where(MileageRecord.truck_id == truck_id, MileageRecord.tenant_id == tenant_id)
            .order_by(MileageRecord.record_date)
        )
    ).scalars().all()
    if len(mileage) >= 2:
        first, last = mileage[0], mileage[-1]
        days = max((last.record_date - first.record_date).days, 1)
        miles = max(last.odometer_reading - first.odometer_reading, 0)
        daily = miles / days
        annual = daily * 365
        await upsert_fleet_metric(
            db,
            entity_type="truck",
            entity_id=truck_id,
            metric_name="odometer_daily_miles_avg",
            value=Decimal(str(round(daily, 4))),
            period_type="all_time",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        await upsert_fleet_metric(
            db,
            entity_type="truck",
            entity_id=truck_id,
            metric_name="odometer_annual_miles_expected",
            value=Decimal(str(round(annual, 4))),
            period_type="all_time",
            period_start=period_start,
            period_end=period_end,
            tenant_id=tenant_id,
        )
        written += 2
        if miles > 0 and total_spend:
            cpm = float(total_spend) / miles
            await upsert_fleet_metric(
                db,
                entity_type="truck",
                entity_id=truck_id,
                metric_name="cost_per_mile",
                value=Decimal(str(round(cpm, 4))),
                period_type="all_time",
                period_start=period_start,
                period_end=period_end,
                tenant_id=tenant_id,
            )
            written += 1

    return written
