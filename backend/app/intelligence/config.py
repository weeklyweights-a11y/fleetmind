"""Thresholds and constants for anomaly detection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceThresholds:
    cost_spike_sd_warning: float = 2.0
    cost_spike_sd_critical: float = 3.0
    cost_spike_auto_resolve_sd: float = 1.0
    vendor_cost_increase_pct: float = 125.0
    efficiency_decline_pct: float = 20.0
    recurring_issue_count: int = 3
    recurring_issue_months: int = 6
    unknown_document_count: int = 3
    unknown_document_days: int = 30
    planned_overhaul_cost: float = 10_000.0
    compliance_info_days_min: int = 30
    compliance_info_days_max: int = 60
    compliance_warning_days_min: int = 7
    compliance_warning_days_max: int = 30
    compliance_critical_days_max: int = 7
    compliance_scan_window_days: int = 90
    vendor_min_events: int = 3
    unresolved_item_max_age_days: int = 30
    conversation_dedup_days: int = 7


THRESHOLDS = IntelligenceThresholds()

ACTIVE_ANOMALY_STATUSES = frozenset({"new", "acknowledged", "investigating"})
TERMINAL_ANOMALY_STATUSES = frozenset({"dismissed", "resolved"})

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
