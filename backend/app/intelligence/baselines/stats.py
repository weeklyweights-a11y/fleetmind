"""Statistical helpers for baseline computation."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Sequence


def mean(values: Sequence[float | Decimal]) -> float:
    if not values:
        return 0.0
    return float(sum(float(v) for v in values) / len(values))


def stdev(values: Sequence[float | Decimal]) -> float:
    if len(values) < 2:
        return 0.0
    try:
        return float(statistics.stdev(float(v) for v in values))
    except statistics.StatisticsError:
        return 0.0


def monthly_buckets(
    events: Sequence[tuple[date, float | Decimal]],
) -> dict[str, list[float]]:
    """Group (service_date, value) into YYYY-MM buckets."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for svc_date, value in events:
        key = svc_date.strftime("%Y-%m")
        buckets[key].append(float(value))
    return buckets


def monthly_spend_stats(monthly_totals: list[float]) -> dict[str, float]:
    if not monthly_totals:
        return {"mean": 0.0, "sd": 0.0, "count": 0.0, "min": 0.0, "max": 0.0, "trend": 0.0}
    m = mean(monthly_totals)
    sd = stdev(monthly_totals)
    trend = 0.0
    if len(monthly_totals) >= 6:
        recent = mean(monthly_totals[-3:])
        prior = mean(monthly_totals[-6:-3])
        if recent > prior * 1.05:
            trend = 1.0
        elif recent < prior * 0.95:
            trend = -1.0
    elif len(monthly_totals) >= 2:
        if monthly_totals[-1] > monthly_totals[-2]:
            trend = 1.0
        elif monthly_totals[-1] < monthly_totals[-2]:
            trend = -1.0
    return {
        "mean": m,
        "sd": sd,
        "count": float(len(monthly_totals)),
        "min": min(monthly_totals),
        "max": max(monthly_totals),
        "trend": trend,
        "latest": monthly_totals[-1] if monthly_totals else 0.0,
    }


def mom_change_pct(values: list[float]) -> float:
    if len(values) < 2 or values[-2] == 0:
        return 0.0
    return 100.0 * (values[-1] - values[-2]) / values[-2]


def qoq_change_pct(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    recent_q = sum(values[-3:]) / 3
    prior_q = sum(values[-6:-3]) / 3 if len(values) >= 6 else sum(values[:-3]) / max(len(values) - 3, 1)
    if prior_q == 0:
        return 0.0
    return 100.0 * (recent_q - prior_q) / prior_q
