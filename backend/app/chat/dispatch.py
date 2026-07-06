"""Map LLM dispatch plans to Phase 3 sub-agent functions."""

from __future__ import annotations

import inspect
import uuid
from datetime import date, datetime
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import graph_queries, memory_search as memory_search_agent
from app.agents._lookup import (
    resolve_driver_id,
    resolve_truck_id,
    resolve_truck_ids_from_list,
    resolve_vendor_by_name,
    resolve_vendor_id,
)
from app.agents._parallel import gather_with_sessions
from app.agents.anomaly_actions import update_anomaly_status
from app.agents.anomaly_feed import get_anomaly_feed
from app.agents.compliance_matrix import get_compliance_matrix
from app.agents.driver_profile import get_driver_profile
from app.agents.fleet_comparison import get_fleet_comparison
from app.agents.fleet_maintenance_summary import get_fleet_maintenance_summary
from app.agents.fleet_overview import get_fleet_overview
from app.agents.truck_assignment import get_truck_assignment
from app.agents.truck_compliance import get_truck_compliance
from app.agents.truck_documents import get_truck_documents
from app.agents.truck_financials import get_truck_financials
from app.agents.truck_identity import get_truck_identity
from app.agents.truck_maintenance import get_truck_maintenance
from app.agents.vendor_analysis import get_vendor_analysis_detail, get_vendor_analysis_fleet
from app.chat.abbreviate_results import result_summary, serialize_results_for_llm
from app.chat.memory_helpers import get_new_documents_since, get_tracking_items
from app.chat.schemas import DispatchPlanItem, SubAgentResult, ToolsUsedEntry
from app.exceptions import DriverNotFoundError, FleetMindError, TruckNotFoundError, VendorNotFoundError


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
    return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


async def _resolve_truck_param(db: AsyncSession, params: dict[str, Any], tenant_id: int = 1) -> uuid.UUID:
    if params.get("truck_id") is not None:
        val = params["truck_id"]
        if isinstance(val, int):
            return await resolve_truck_id(db, unit=val, tenant_id=tenant_id)
        return await resolve_truck_id(db, identifier=str(val), tenant_id=tenant_id)
    if params.get("unit") is not None:
        return await resolve_truck_id(db, unit=int(params["unit"]), tenant_id=tenant_id)
    if params.get("unit_number") is not None:
        return await resolve_truck_id(db, unit=int(params["unit_number"]), tenant_id=tenant_id)
    raise TruckNotFoundError("missing truck_id")


async def normalize_params(
    fn_name: str,
    params: dict[str, Any],
    db: AsyncSession,
    tenant_id: int = 1,
) -> dict[str, Any]:
    out = dict(params or {})
    truck_fns = {
        "get_truck_identity",
        "get_truck_assignment",
        "get_truck_maintenance",
        "get_truck_compliance",
        "get_truck_financials",
        "get_truck_documents",
        "get_truck_graph",
    }
    if fn_name in truck_fns:
        truck_uuid = await _resolve_truck_param(db, out, tenant_id)
        out["truck_id"] = truck_uuid
        out.pop("unit", None)
        out.pop("unit_number", None)

    if fn_name == "get_truck_maintenance":
        time_range = out.pop("time_range", None) or out.pop("time_scope", None)
        if isinstance(time_range, dict):
            out["start_date"] = _parse_date(time_range.get("start_date") or out.get("start_date"))
            out["end_date"] = _parse_date(time_range.get("end_date") or out.get("end_date"))
        else:
            out["start_date"] = _parse_date(out.get("start_date"))
            out["end_date"] = _parse_date(out.get("end_date"))

    if fn_name == "get_driver_profile":
        ident = out.get("driver_id") or out.get("code") or out.get("identifier")
        out["driver_id"] = await resolve_driver_id(db, identifier=str(ident) if ident else None, tenant_id=tenant_id)

    if fn_name == "get_vendor_analysis_detail":
        if out.get("vendor_name") and not out.get("vendor_id"):
            out["vendor_id"] = await resolve_vendor_by_name(db, str(out["vendor_name"]), tenant_id)
        elif out.get("vendor_id"):
            out["vendor_id"] = await resolve_vendor_id(db, str(out["vendor_id"]), tenant_id)

    if fn_name == "get_entity_connections":
        entity_type = out.get("entity_type") or out.get("type") or "vendor"
        entity_id = out.get("entity_id") or out.get("id")
        if entity_type == "vendor" and entity_id and not _is_uuid(str(entity_id)):
            entity_id = await resolve_vendor_by_name(db, str(entity_id), tenant_id)
        elif entity_type == "truck" and entity_id:
            if not _is_uuid(str(entity_id)):
                entity_id = await resolve_truck_id(db, identifier=str(entity_id), tenant_id=tenant_id)
        elif entity_type == "driver" and entity_id and not _is_uuid(str(entity_id)):
            entity_id = await resolve_driver_id(db, identifier=str(entity_id), tenant_id=tenant_id)
        out["entity_type"] = entity_type
        out["entity_id"] = str(entity_id)

    if fn_name == "get_fleet_comparison" and out.get("trucks"):
        out["truck_ids"] = await resolve_truck_ids_from_list(db, list(out["trucks"]), tenant_id)
        out.pop("trucks", None)

    out.setdefault("tenant_id", tenant_id)
    return out


DISPATCH_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_truck_identity": get_truck_identity,
    "get_truck_assignment": get_truck_assignment,
    "get_truck_maintenance": get_truck_maintenance,
    "get_truck_compliance": get_truck_compliance,
    "get_truck_financials": get_truck_financials,
    "get_truck_documents": get_truck_documents,
    "get_fleet_overview": get_fleet_overview,
    "get_fleet_comparison": get_fleet_comparison,
    "get_fleet_maintenance_summary": get_fleet_maintenance_summary,
    "get_compliance_matrix": get_compliance_matrix,
    "get_driver_profile": get_driver_profile,
    "get_vendor_analysis_fleet": get_vendor_analysis_fleet,
    "get_vendor_analysis_detail": get_vendor_analysis_detail,
    "get_anomaly_feed": get_anomaly_feed,
    "update_anomaly_status": update_anomaly_status,
    "get_truck_graph": graph_queries.get_truck_graph,
    "get_fleet_graph": graph_queries.get_fleet_graph,
    "get_entity_connections": graph_queries.get_entity_connections,
    "get_memory_search": memory_search_agent.get_memory_search,
    "get_tracking_items": get_tracking_items,
    "get_new_documents_since": get_new_documents_since,
}


def _callable_kwargs(fn: Callable[..., Any], params: dict[str, Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    allowed = set(sig.parameters.keys()) - {"db"}
    return {k: v for k, v in params.items() if k in allowed}


async def _run_dispatch_item(db: AsyncSession, item: DispatchPlanItem, tenant_id: int) -> tuple[str, SubAgentResult]:
    fn = DISPATCH_REGISTRY.get(item.function)
    if fn is None:
        return item.function, SubAgentResult(function=item.function, status="error", error="unknown function")
    try:
        norm = await normalize_params(item.function, item.params, db, tenant_id)
        if item.function == "get_memory_search":
            result = await fn(
                db,
                str(norm.get("query") or item.params.get("query") or ""),
                norm.get("operator_name") or item.params.get("operator_name"),
                tenant_id,
            )
        elif item.function == "get_tracking_items":
            result = await fn(
                db,
                str(norm.get("operator_name") or item.params.get("operator_name") or "default"),
                tenant_id,
            )
        elif item.function == "update_anomaly_status":
            result = await fn(
                db,
                uuid.UUID(str(norm.get("anomaly_id") or item.params.get("anomaly_id"))),
                str(norm.get("status") or item.params.get("status")),
                operator_name=str(norm.get("operator_name") or item.params.get("operator_name") or "default"),
                reason=norm.get("reason") or item.params.get("reason"),
                tenant_id=tenant_id,
            )
        elif item.function == "get_new_documents_since":
            result = await fn(
                db,
                norm.get("entities_discussed") or item.params.get("entities_discussed"),
                _parse_datetime(norm.get("ended_at") or item.params.get("ended_at")),
                tenant_id,
            )
        else:
            kwargs = _callable_kwargs(fn, norm)
            result = await fn(db, **kwargs)
        dumped = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        empty = not dumped
        return item.function, SubAgentResult(
            function=item.function,
            status="ok",
            result=dumped if isinstance(dumped, dict) else {"data": dumped},
            empty=empty,
        )
    except (TruckNotFoundError, DriverNotFoundError, VendorNotFoundError, FleetMindError) as exc:
        return item.function, SubAgentResult(function=item.function, status="error", error=str(exc), empty=True)
    except Exception as exc:
        return item.function, SubAgentResult(function=item.function, status="error", error=str(exc), empty=True)


async def execute_dispatch_plan(plan: list[DispatchPlanItem], tenant_id: int = 1) -> dict[str, SubAgentResult]:
    if not plan:
        return {}

    fns = []
    for item in plan:
        async def bound(db: AsyncSession, item=item):
            return await _run_dispatch_item(db, item, tenant_id)

        fns.append(bound)

    pairs = await gather_with_sessions(fns)
    out: dict[str, SubAgentResult] = {}
    for idx, (name, res) in enumerate(pairs):
        key = name if name not in out else f"{name}_{idx}"
        out[key] = res
    return out


def build_tools_used(plan: list[DispatchPlanItem], results: dict[str, SubAgentResult]) -> list[ToolsUsedEntry]:
    entries: list[ToolsUsedEntry] = []
    result_items = list(results.values())
    for idx, item in enumerate(plan):
        res = results.get(item.function) or (result_items[idx] if idx < len(result_items) else None)
        entries.append(
            ToolsUsedEntry(
                function=item.function,
                params=item.params,
                status=res.status if res else "error",
                result_summary=result_summary(item.function, res.result if res else None, res.error if res else None),
            )
        )
    return entries


def results_for_synthesis(results: dict[str, SubAgentResult]) -> dict[str, Any]:
    payload = {k: v.model_dump(mode="json") for k, v in results.items()}
    return serialize_results_for_llm(payload)
