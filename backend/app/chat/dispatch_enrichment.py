"""Rule-based dispatch plan enrichment when LLM output is thin or ambiguous."""

from __future__ import annotations

import re
from typing import Any

from app.chat import intents
from app.chat.schemas import ChatGraphState, DashboardContext, DispatchPlanItem, QueryUnderstanding
from app.database import async_session_factory


def _message_lower(state: ChatGraphState) -> str:
    return (state.get("message") or "").strip().lower()


def _has_function(plan: list[DispatchPlanItem], name: str) -> bool:
    return any(p.function == name for p in plan)


def _dashboard_truck_unit(dashboard: DashboardContext | None) -> int | None:
    if not dashboard or not dashboard.current_entity:
        return None
    ent = dashboard.current_entity
    unit = ent.get("unit") or ent.get("unit_number")
    if unit is not None:
        try:
            return int(unit)
        except (TypeError, ValueError):
            return None
    ident = ent.get("identifier") or ent.get("id")
    if ident is not None and str(ident).isdigit():
        return int(ident)
    return None


def _truck_units_in_message(msg: str) -> list[int]:
    return [int(m) for m in re.findall(r"\btruck\s*#?\s*(\d+)\b", msg, flags=re.I)]


async def enrich_query_understanding(state: ChatGraphState, qu: QueryUnderstanding) -> QueryUnderstanding:
    msg = _message_lower(state)
    dashboard = state.get("dashboard_context")
    if isinstance(dashboard, dict):
        dashboard = DashboardContext.model_validate(dashboard)
    plan = list(qu.dispatch_plan)
    entities = list(qu.entities)
    intent = qu.intent
    confidence = qu.confidence

    greeting_re = re.compile(r"^(good\s+(morning|afternoon|evening)|hello|hi|hey)\b", re.I)
    if greeting_re.match(msg.strip()):
        return qu.model_copy(
            update={
                "intent": intents.GREETING,
                "dispatch_plan": [],
                "confidence": max(confidence, 0.95),
            }
        )

    if "tracking" in msg or "was tracking" in msg or "keep an eye" in msg:
        if not _has_function(plan, "get_tracking_items"):
            plan.append(DispatchPlanItem(function="get_tracking_items", params={}))
        if not _has_function(plan, "get_anomaly_feed"):
            plan.append(DispatchPlanItem(function="get_anomaly_feed", params={"follow_up": True}))
        if not _has_function(plan, "get_memory_search"):
            plan.append(
                DispatchPlanItem(
                    function="get_memory_search",
                    params={"query": state.get("message", "tracking items")},
                )
            )
        intent = intents.HISTORY_RECALL
        confidence = max(confidence, 0.85)

    elif "worry about" in msg:
        unit = _dashboard_truck_unit(dashboard)
        if unit is not None and ("here" in msg or dashboard):
            async with async_session_factory() as db:
                from app.agents._lookup import resolve_truck_id

                try:
                    truck_id = await resolve_truck_id(db, unit=unit)
                except Exception:
                    truck_id = None
                await db.commit()
            if truck_id:
                if not _has_function(plan, "get_truck_compliance"):
                    plan.append(DispatchPlanItem(function="get_truck_compliance", params={"unit": unit}))
                if not _has_function(plan, "get_anomaly_feed"):
                    plan.append(
                        DispatchPlanItem(
                            function="get_anomaly_feed",
                            params={"entity_type": "truck", "entity_id": str(truck_id)},
                        )
                    )
                intent = intents.COMPLIANCE_CHECK
                confidence = max(confidence, 0.9)
        elif not _has_function(plan, "get_anomaly_feed"):
            plan.append(DispatchPlanItem(function="get_anomaly_feed", params={}))
            intent = intents.COMPLIANCE_CHECK
            confidence = max(confidence, 0.85)

    elif re.search(r"\bcompare\b", msg):
        units = _truck_units_in_message(msg) or [
            int(m) for m in re.findall(r"\b(\d{2,3})\b", msg) if 1 <= int(m) <= 999
        ][:3]
        if len(units) >= 2 and not _has_function(plan, "get_fleet_comparison"):
            plan.append(DispatchPlanItem(function="get_fleet_comparison", params={"units": units}))
            intent = intents.COMPARISON
            confidence = max(confidence, 0.85)

    elif re.search(r"tell me about truck\s*#?\s*\d+", msg, re.I):
        m = re.search(r"truck\s*#?\s*(\d+)", msg, re.I)
        if m:
            unit = int(m.group(1))
            names = {
                "get_truck_identity",
                "get_truck_assignment",
                "get_truck_maintenance",
                "get_truck_compliance",
                "get_truck_financials",
            }
            for fn in names:
                if not _has_function(plan, fn):
                    plan.append(DispatchPlanItem(function=fn, params={"unit": unit}))
            intent = intents.ENTITY_OVERVIEW
            confidence = max(confidence, 0.9)

    elif re.search(r"last time|talk about last|we discuss", msg):
        if not _has_function(plan, "get_memory_search"):
            plan.append(
                DispatchPlanItem(
                    function="get_memory_search",
                    params={"query": state.get("message", "previous conversation")},
                )
            )
        intent = intents.HISTORY_RECALL
        confidence = max(confidence, 0.85)

    if plan and confidence < 0.6:
        confidence = 0.75

    return qu.model_copy(
        update={
            "dispatch_plan": plan,
            "entities": entities,
            "intent": intent,
            "confidence": confidence,
        }
    )
