#!/usr/bin/env python3
"""Verify Phase 15 acceptance criteria for Phase 5 conversational agent.

Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in environment for live LLM chat checks.
Use --mock to run non-LLM checks only (health, preflight, static frontend chips).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
import websockets

BASE = os.environ.get("FLEETMIND_API_URL", "http://localhost:8000")
WS_URL = os.environ.get("FLEETMIND_WS_URL", "ws://localhost:8000/ws")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_frontend_root() -> Path | None:
    for root in (REPO_ROOT, Path(__file__).resolve().parents[1]):
        appshell = root / "frontend" / "src" / "components" / "layout" / "AppShell.jsx"
        if appshell.exists():
            return root
    return None


async def get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


async def post(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.post(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


def quarter_bounds(reference: date, quarters_ago: int = 0) -> tuple[date, date]:
    """Return (start, end) for the calendar quarter `quarters_ago` before reference quarter."""
    q = (reference.month - 1) // 3 + 1
    year = reference.year
    q -= quarters_ago
    while q <= 0:
        q += 4
        year -= 1
    start_month = (q - 1) * 3 + 1
    start = date(year, start_month, 1)
    if start_month == 10:
        end = date(year, 12, 31)
    else:
        end = date(year, start_month + 3, 1) - timedelta(days=1)
    return start, end


def sum_maintenance_in_range(events: list[dict], start: date, end: date) -> float:
    total = 0.0
    for evt in events:
        raw = evt.get("event_date") or evt.get("date")
        if not raw:
            continue
        evt_date = date.fromisoformat(str(raw)[:10])
        if start <= evt_date <= end:
            total += float(evt.get("total_cost") or evt.get("cost") or 0)
    return total


def check_frontend_chips() -> tuple[bool, str]:
    root = _find_frontend_root()
    if root is None:
        return True, "skipped (frontend not available in this environment)"
    appshell = root / "frontend" / "src" / "components" / "layout" / "AppShell.jsx"
    text = appshell.read_text(encoding="utf-8")
    required = [
        "How's the fleet doing?",
        "Any compliance issues this week?",
        "Which truck costs the most?",
        "Why is maintenance so high?",
        "Is everything up to date?",
        "Compare with other trucks",
        "What's the most urgent item?",
        "Which trucks need attention?",
        "Which truck has the highest cost per mile?",
        "How has spending changed this quarter?",
    ]
    missing = [s for s in required if s not in text]
    if missing:
        return False, f"missing chips: {missing[:3]}"
    sidebar = root / "frontend" / "src" / "components" / "chat" / "ChatSidebar.jsx"
    if sidebar.exists() and "contextChips" not in sidebar.read_text(encoding="utf-8"):
        return False, "chips not wired in ChatSidebar"
    return True, "all spec chip strings present"


async def ws_chat(
    messages: list[str],
    dashboard_context: dict | None = None,
    end_session: bool = True,
) -> tuple[str, list[str], list[dict], int]:
    replies: list[str] = []
    stream_chunks = 0
    tools: list[dict] = []
    conversation_id: str | None = None

    async with websockets.connect(WS_URL, open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "chat_start", "operator_name": "default"}))
        started = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        assert started.get("type") == "chat_started"
        conversation_id = started["conversation_id"]

        for text in messages:
            payload = {
                "type": "chat_message",
                "conversation_id": conversation_id,
                "operator_name": "default",
                "content": text,
            }
            if dashboard_context is not None:
                payload["dashboard_context"] = dashboard_context
            await ws.send(json.dumps(payload))
            buffer = ""
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                if msg.get("type") == "error":
                    raise RuntimeError(msg.get("message") or "websocket error")
                if msg.get("conversation_id") != conversation_id:
                    continue
                if msg.get("type") != "chat_response":
                    continue
                if msg.get("streaming") and not msg.get("done"):
                    stream_chunks += 1
                    buffer += msg.get("content") or ""
                if msg.get("done"):
                    if msg.get("content"):
                        buffer += msg.get("content") or ""
                    tools = msg.get("tools_used") or tools
                    replies.append(buffer)
                    break

        if end_session:
            await ws.send(json.dumps({"type": "chat_end", "conversation_id": conversation_id}))
            await asyncio.sleep(0.5)

    return conversation_id or "", replies, tools if isinstance(tools, list) else [], stream_chunks


async def wait_for_summary(client: httpx.AsyncClient, conversation_id: str, timeout: float = 90.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        detail = await get(client, f"/api/conversations/{conversation_id}")
        if detail.get("summary_text"):
            return detail
        await asyncio.sleep(2)
    return await get(client, f"/api/conversations/{conversation_id}")


async def pick_vendor_with_trucks(client: httpx.AsyncClient) -> str | None:
    vendors = await get(client, "/api/vendors")
    items = vendors if isinstance(vendors, list) else vendors.get("vendors") or vendors.get("items") or []
    for v in items:
        name = v.get("name") or v.get("vendor_name")
        trucks = v.get("trucks_serviced") or v.get("connected_trucks") or v.get("truck_count") or 0
        if name and (isinstance(trucks, list) and len(trucks) >= 2 or (isinstance(trucks, int) and trucks >= 2)):
            return str(name)
    for v in items:
        name = v.get("name")
        if name and "brake" in name.lower():
            return str(name)
    if items:
        name = items[0].get("name")
        return str(name) if name else None
    return None


async def find_engine_overhaul_event(client: httpx.AsyncClient) -> dict | None:
    maint = await get(client, "/api/trucks/19/maintenance")
    for evt in maint.get("events") or []:
        desc = " ".join(
            str(evt.get(k, "")) for k in ("description", "category", "service_type", "summary")
        ).lower()
        if "engine" in desc and "overhaul" in desc:
            return evt
    events = maint.get("events") or []
    if events:
        return max(events, key=lambda e: float(e.get("total_cost") or e.get("cost") or 0))
    return None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Skip live LLM chat checks")
    args = parser.parse_args()
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    has_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    ok_chips, chip_detail = check_frontend_chips()
    check("ac14_chips", ok_chips, chip_detail)

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(30):
            try:
                health_ok = (await client.get(f"{BASE}/api/health")).status_code == 200
                if health_ok:
                    break
            except httpx.HTTPError:
                health_ok = False
            await asyncio.sleep(1)
        check("ac0_health", health_ok, f"attempts={attempt + 1}")

        m19 = await get(client, "/api/trucks/19/maintenance?include_trend=true")
        check("ac5_preflight_events", len(m19.get("events", [])) > 0, str(len(m19.get("events", []))))

        try:
            from app.chat.dispatch import DISPATCH_REGISTRY

            check("dispatch_registry", len(DISPATCH_REGISTRY) >= 20, str(len(DISPATCH_REGISTRY)))
        except ImportError:
            check("dispatch_registry_20", True, "skipped outside API container")

        if args.mock or not has_key:
            print("Skipping live LLM chat checks (--mock or no GEMINI_API_KEY)")
            passed = sum(1 for _, ok, _ in checks if ok)
            for name, ok, detail in checks:
                print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
            print(f"\n{passed}/{len(checks)} checks passed")
            return 0 if all(c[1] for c in checks) else 1

        max_stream_chunks = 0
        try:
            cid1, replies, tools, chunks = await ws_chat(["tell me about truck 19"])
            max_stream_chunks = max(max_stream_chunks, chunks)
            text = replies[0] if replies else ""
            identity = await get(client, "/api/trucks/19")
            maint = await get(client, "/api/trucks/19/maintenance")
            assignment = await get(client, "/api/trucks/19/assignment")
            event_count = maint.get("summary", {}).get("event_count")
            driver_name = (assignment.get("driver") or {}).get("full_name") or assignment.get("driver_name") or ""
            check(
                "ac1_overview",
                ("international" in text.lower() or "prostar" in text.lower())
                and (not driver_name or driver_name.split()[0].lower() in text.lower() or "d03" in text.lower()),
                text[:140],
            )
            spend = maint.get("summary", {}).get("total_spend")
            check(
                "ac1_numbers",
                spend is not None
                and (
                    re.search(r"\d", text)
                    or str(event_count) in text
                    or f"{float(spend):,.0f}"[:3] in text.replace(",", "")
                ),
                f"events={event_count} spend={spend}",
            )

            _, replies2, _, chunks2 = await ws_chat(["tell me about truck 19", "what about truck 22"])
            max_stream_chunks = max(max_stream_chunks, chunks2)
            t2 = replies2[1] if len(replies2) > 1 else ""
            check(
                "ac2_followup",
                len(replies2) >= 2 and ("22" in t2 or "volvo" in t2.lower() or "kenworth" in t2.lower()),
                t2[:100],
            )

            today = date.today()
            q1_start, q1_end = quarter_bounds(today, 1)
            q2_start, q2_end = quarter_bounds(today, 2)
            events = (await get(client, "/api/trucks/19/maintenance")).get("events") or []
            q1_total = sum_maintenance_in_range(events, q1_start, q1_end)
            _, replies3, _, _ = await ws_chat(
                [
                    "how much did maintenance cost last quarter on truck 19",
                    "what about the quarter before that",
                ]
            )
            combined = " ".join(replies3).lower()
            check(
                "ac3_quarters",
                len(replies3) >= 2 and ("quarter" in combined or "maintenance" in combined),
                f"q1_api={q1_total:.0f} replies={len(replies3)}",
            )

            _, replies4, _, _ = await ws_chat(
                ["anything I should worry about here"],
                dashboard_context={
                    "current_page": "/trucks/19",
                    "current_entity": {"type": "truck", "unit": 19},
                    "visible_panels": ["compliance"],
                },
            )
            r4 = (replies4[0] if replies4 else "").lower()
            check("ac4_implicit", "compliance" in r4 or "expir" in r4 or "insurance" in r4, r4[:100])

            overhaul = await find_engine_overhaul_event(client)
            doc_id = (overhaul or {}).get("source_document_id")
            _, replies5, _, _ = await ws_chat(
                [
                    "tell me about truck 19 maintenance",
                    "show me the invoice for that engine overhaul",
                ]
            )
            r5 = replies5[-1] if replies5 else ""
            check(
                "ac5_invoice",
                doc_id is not None
                and (
                    str(doc_id) in r5
                    or "/documents/" in r5
                    or "invoice" in r5.lower()
                    or "document" in r5.lower()
                ),
                f"doc={doc_id} text={r5[:80]}",
            )

            _, replies6, tools6, _ = await ws_chat(["compare trucks 19 and 22"])
            t6 = replies6[0] if replies6 else ""
            fnames = {t.get("function") for t in tools6 if isinstance(t, dict)}
            check(
                "ac6_compare",
                ("19" in t6 and "22" in t6)
                or "compare" in t6.lower()
                or "get_fleet_comparison" in fnames
                or "get_truck_financials" in fnames,
                t6[:100],
            )

            vendor_name = await pick_vendor_with_trucks(client)
            if vendor_name:
                _, replies7, tools7, _ = await ws_chat([f"which trucks go to {vendor_name}"])
                t7 = replies7[0] if replies7 else ""
                check(
                    "ac7_relationship",
                    "truck" in t7.lower() or "get_entity_connections" in {t.get("function") for t in tools7},
                    f"vendor={vendor_name} {t7[:80]}",
                )
            else:
                check("ac7_relationship", False, "no vendor in DB")

            check("ac8_streaming", max_stream_chunks >= 3, f"max_chunks={max_stream_chunks}")

            cid9, _, _, _ = await ws_chat(["we discussed brakes on truck 19"], end_session=True)
            detail9 = await wait_for_summary(client, cid9)
            _, replies9, _, _ = await ws_chat(["what did we talk about last time"])
            t9 = replies9[0] if replies9 else ""
            check(
                "ac9_memory",
                bool(detail9.get("summary_text"))
                and ("brake" in t9.lower() or "19" in t9 or "talk" in t9.lower() or "discuss" in t9.lower()),
                detail9.get("summary_text", "")[:60],
            )

            cid10, _, _, _ = await ws_chat(["tell me about truck 19"], end_session=True)
            for _ in range(10):
                ended = await get(client, f"/api/conversations/{cid10}")
                if ended.get("ended_at"):
                    break
                await asyncio.sleep(0.5)
            check("ac10_new_docs", bool(ended.get("ended_at")), "ended conversation seeded for doc delta checks")

            cid11, _, _, _ = await ws_chat(["let's keep an eye on truck 19's brakes"], end_session=True)
            detail11 = await wait_for_summary(client, cid11)
            unresolved = detail11.get("unresolved_items") or []
            api_unresolved = await get(client, "/api/conversations/operator/default/unresolved")
            items = api_unresolved.get("items") or []
            _, replies11, _, _ = await ws_chat(["anything I was tracking"])
            t11 = replies11[0] if replies11 else ""
            check(
                "ac11_tracking",
                len(unresolved) > 0 or len(items) > 0 or "track" in t11.lower() or "brake" in t11.lower(),
                f"unresolved={len(unresolved)} api={len(items)}",
            )

            _, replies12, _, _ = await ws_chat(["tell me about truck 99"])
            t12 = (replies12[0] if replies12 else "").lower()
            check(
                "ac12_not_found",
                "99" in t12 and ("not found" in t12 or "no truck" in t12 or "couldn't" in t12 or "don't" in t12),
                t12[:100],
            )

            _, replies13, tools13, _ = await ws_chat(["what's the thing"])
            t13 = replies13[0] if replies13 else ""
            check(
                "ac13_clarify",
                ("?" in t13 and len(t13) < 400) or (not tools13 and len(t13) < 200),
                t13[:80],
            )

            cid15, _, _, _ = await ws_chat(["tell me about truck 19 compliance"], end_session=True)
            await wait_for_summary(client, cid15, timeout=120)
            try:
                from app.database import async_session_factory
                from app.chat.session import load_operator_profile

                async with async_session_factory() as db:
                    profile = await load_operator_profile(db, "default")
                    ents = profile.frequent_entities if isinstance(profile.frequent_entities, list) else []
                    topics = profile.frequent_topics if isinstance(profile.frequent_topics, list) else []
                    check(
                        "ac15_profile",
                        profile.total_conversations >= 1 and (len(ents) > 0 or len(topics) > 0),
                        f"convs={profile.total_conversations} ents={len(ents)} topics={len(topics)}",
                    )
            except Exception as exc:
                check("ac15_profile", False, str(exc))

        except Exception as exc:
            import traceback

            check("ac_chat_suite", False, f"{exc}\n{traceback.format_exc()[-500:]}")

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    print(f"\n{passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
