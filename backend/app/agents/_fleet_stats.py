"""Fleet statistics helpers."""

from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Sequence


def safe_mean(values: Sequence[float | Decimal]) -> float:
    if not values:
        return 0.0
    return float(sum(float(v) for v in values) / len(values))


def percentile_rank(value: float, population: Sequence[float]) -> int:
    if not population:
        return 1
    below = sum(1 for v in population if v < value)
    return int(round(100 * below / len(population))) + 1


def detect_outliers(values: dict[str, float], sigma: float = 2.0) -> list[str]:
    if len(values) < 2:
        return []
    nums = list(values.values())
    mean = statistics.mean(nums)
    try:
        stdev = statistics.stdev(nums)
    except statistics.StatisticsError:
        return []
    if stdev == 0:
        return []
    flags: list[str] = []
    for key, val in values.items():
        if val > mean + sigma * stdev:
            flags.append(key)
    return flags


def rank_desc(values: list[tuple[int, float]]) -> list[int]:
    """Rank unit numbers by value descending. Input: (unit_number, metric)."""
    sorted_units = [u for u, _ in sorted(values, key=lambda x: x[1], reverse=True)]
    return sorted_units
