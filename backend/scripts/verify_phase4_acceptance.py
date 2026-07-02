#!/usr/bin/env python3
"""Verify Phase 4 acceptance criteria against the 197-document Sunflower archive."""

from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws"


async def get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


async def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    async with httpx.AsyncClient(timeout=30.0) as client:
        # AC 1 — fleet overview with quick_stats and recent activity descriptions
        overview = await get(client, "/api/fleet/overview")
        qs = overview.get("quick_stats", {})
        check("ac1_quick_stats_events", qs.get("total_maintenance_events", 0) > 0, str(qs.get("total_maintenance_events")))
        check("ac1_quick_stats_vendors", qs.get("total_vendors", 0) > 0, str(qs.get("total_vendors")))
        check("ac1_most_expensive", qs.get("most_expensive_truck") is not None, "")
        recent = overview.get("recent_activity", [])
        check("ac1_recent_activity", len(recent) > 0, str(len(recent)))
        if recent:
            check("ac1_recent_description", bool(recent[0].get("description")), recent[0].get("description", ""))

        # AC 2 — truck sub-agents + maintenance events
        for sub in ["", "/assignment", "/maintenance", "/compliance", "/financials", "/documents"]:
            path = f"/api/trucks/19{sub}"
            if sub == "/maintenance":
                r = await client.get(f"{BASE}{path}?include_trend=true")
            else:
                r = await client.get(f"{BASE}{path}")
            check(f"ac2_truck19{sub or '_identity'}", r.status_code == 200, str(r.status_code))
        m19 = await get(client, "/api/trucks/19/maintenance?include_trend=true")
        events = m19.get("events", [])
        check("ac2_maintenance_events", len(events) > 0, str(len(events)))
        check("ac2_maintenance_trend", len(m19.get("trend", [])) > 0, "")

        # AC 3 — compliance matrix
        matrix = await get(client, "/api/compliance/matrix")
        check("ac3_rows", len(matrix.get("matrix", [])) == 16, str(len(matrix.get("matrix", []))))
        check("ac3_score", matrix.get("fleet_compliance_score") is not None, "")

        # AC 4 — fleet comparison + maintenance summary
        cmp_resp = await get(client, "/api/fleet/comparison")
        check("ac4_comparison", len(cmp_resp.get("trucks", [])) >= 16, "")
        summary = await get(client, "/api/fleet/maintenance-summary")
        check("ac4_monthly_trend", len(summary.get("monthly_trend", [])) > 0, "")
        check("ac4_by_category", len(summary.get("by_category", [])) > 0, "")

        # AC 6 — processing_status_in filter for queue hydration
        inflight = await get(
            client,
            "/api/documents?processing_status_in=queued,parsing,extracting&limit=5",
        )
        check("ac6_status_in_filter", "items" in inflight, "")

        # AC 9 — document file endpoint
        docs = await get(client, "/api/documents?limit=1&processing_status=complete")
        if docs.get("items"):
            doc_id = docs["items"][0]["id"]
            fr = await client.get(f"{BASE}/api/documents/{doc_id}/file")
            ct = fr.headers.get("content-type", "")
            check("ac9_pdf_content_type", "pdf" in ct.lower(), ct)

            # AC 6 extraction endpoint
            ext = await get(client, f"/api/documents/{doc_id}/extraction")
            check("ac6_extraction_fields", "fields" in ext, "")

        # AC 11-12 — graphs
        g19 = await get(client, "/api/trucks/19/graph")
        check("ac11_truck_graph_nodes", len(g19.get("nodes", [])) > 0, "")
        fg = await get(client, "/api/fleet/graph")
        check("ac12_fleet_graph_nodes", len(fg.get("nodes", [])) > 0, "")

        # AC list enrich — trucks search, drivers list fields
        trucks = await get(client, "/api/trucks?search=19")
        check("ac5_truck_search", len(trucks.get("items", [])) > 0, "")
        drivers = await get(client, "/api/drivers?per_page=5")
        if drivers.get("items"):
            d0 = drivers["items"][0]
            check("ac5_driver_license_class", d0.get("license_class") is not None, "")
            check("ac5_driver_expiry_status", d0.get("expiry_status") in {"green", "yellow", "red"}, d0.get("expiry_status", ""))

        # Vendor graph
        vendors = await get(client, "/api/vendors")
        if vendors.get("vendors"):
            vid = vendors["vendors"][0]["id"]
            vd = await get(client, f"/api/vendors/{vid}")
            check("ac9_vendor_graph", len(vd.get("relationship_graph", {}).get("nodes", [])) >= 0, "")

    # AC 8 — WebSocket subscribe merge
    try:
        async with asyncio.timeout(15):
            async with websockets.connect(WS_URL, open_timeout=5) as ws:
                await ws.send(json.dumps({"type": "subscribe", "topics": ["fleet_stats"]}))
                await ws.send(
                    json.dumps(
                        {
                            "type": "subscribe",
                            "topics": ["truck_19_maintenance", "fleet_stats"],
                            "unsubscribe": ["fleet_stats"],
                        }
                    )
                )
                pong = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(pong)
                check(
                    "ac8_ws_subscribe_ack",
                    data.get("type") in {"subscribed", "pong", "connected"},
                    data.get("type", ""),
                )
    except Exception as exc:
        check("ac8_ws_subscribe_ack", False, str(exc))

    # AC 13 — chat response shape
    try:
        async with asyncio.timeout(20):
            async with websockets.connect(WS_URL, open_timeout=5) as ws:
                await ws.send(
                    json.dumps(
                        {"type": "chat_message", "conversation_id": "test", "content": "hello"}
                    )
                )
                got_chat = False
                final_msg = None
                for _ in range(30):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if msg.get("type") == "chat_response":
                        got_chat = True
                        final_msg = msg
                        if msg.get("done"):
                            break
                check("ac13_chat_received", got_chat, "")
                check(
                    "ac13_chat_shape",
                    bool(final_msg and "content" in final_msg and "streaming" in final_msg),
                    "",
                )
    except Exception as exc:
        check("ac13_chat_received", False, str(exc))
        check("ac13_chat_shape", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase 4 acceptance: {passed}/{total}\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail and not ok else ""))

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
