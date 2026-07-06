"""Abbreviate sub-agent results for Redis turn history and audit summaries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def abbreviate_sub_agent_result(fn_name: str, result: Any) -> dict[str, Any]:
    data = _dump(result)
    if fn_name == "get_truck_maintenance":
        events = data.get("events") or []
        top = sorted(events, key=lambda e: float(e.get("total_cost") or 0), reverse=True)[:3]
        return {
            "total_spend": (data.get("summary") or {}).get("total_spend"),
            "event_count": (data.get("summary") or {}).get("event_count"),
            "top_events": [
                {
                    "date": e.get("service_date"),
                    "total_cost": e.get("total_cost"),
                    "vendor_name": e.get("vendor_name"),
                    "document_number": e.get("document_number"),
                    "source_document_id": e.get("source_document_id"),
                    "description": e.get("description"),
                }
                for e in top
            ],
        }
    if fn_name in {"get_truck_financials", "get_truck_compliance", "get_truck_identity", "get_truck_assignment"}:
        return {k: data.get(k) for k in list(data.keys())[:12]}
    if fn_name in {"get_fleet_overview", "get_fleet_comparison", "get_fleet_maintenance_summary"}:
        return {k: data.get(k) for k in list(data.keys())[:15]}
    if fn_name in {"get_truck_graph", "get_fleet_graph", "get_entity_connections"}:
        nodes = data.get("nodes") or []
        return {
            "node_count": len(nodes),
            "nodes_preview": [
                {"type": n.get("type"), "label": n.get("label"), "id": n.get("id")}
                for n in nodes[:20]
            ],
        }
    if fn_name == "get_memory_search":
        matches = data.get("matching_conversations") or []
        return {"match_count": len(matches), "matches": matches[:3]}
    return {k: data.get(k) for k in list(data.keys())[:10]}


def result_summary(fn_name: str, result: Any, error: str | None = None) -> str:
    if error:
        return f"error: {error[:120]}"
    abbr = abbreviate_sub_agent_result(fn_name, result)
    if fn_name == "get_truck_maintenance":
        spend = abbr.get("total_spend")
        count = abbr.get("event_count")
        return f"maintenance spend={spend}, events={count}"
    if fn_name == "get_truck_identity":
        ident = abbr.get("identity") or abbr
        return f"unit {ident.get('unit_number')} {ident.get('make')} {ident.get('model')}"
    if fn_name == "get_memory_search":
        return f"{abbr.get('match_count', 0)} matching conversations"
    return str(abbr)[:200]


def serialize_results_for_llm(results: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in results.items():
        if isinstance(val, BaseModel):
            out[key] = val.model_dump(mode="json")
        elif isinstance(val, dict):
            if "result" in val and isinstance(val["result"], BaseModel):
                out[key] = {**val, "result": val["result"].model_dump(mode="json")}
            else:
                out[key] = val
        else:
            out[key] = _dump(val)
    return out
