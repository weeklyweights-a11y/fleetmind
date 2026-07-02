#!/usr/bin/env python3
"""Verify Phase 3 acceptance criteria against the 197-document Sunflower archive."""

from __future__ import annotations

import asyncio
import sys
import time

import httpx

BASE = "http://localhost:8000"


async def get(client: httpx.AsyncClient, path: str) -> dict:
    r = await client.get(f"{BASE}{path}")
    r.raise_for_status()
    return r.json()


async def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    async with httpx.AsyncClient(timeout=30.0) as client:
        # AC 1 — fleet overview
        overview = await get(client, "/api/fleet/overview")
        comp = overview.get("fleet_composition", {})
        check("ac1_trucks", comp.get("total_trucks") == 20, str(comp.get("total_trucks")))
        check("ac1_active", comp.get("active") == 16, str(comp.get("active")))
        check("ac1_sold", comp.get("sold") == 4, str(comp.get("sold")))
        check("ac1_inactive", comp.get("inactive") == 0, str(comp.get("inactive")))
        check("ac1_drivers", comp.get("total_drivers") == 20, str(comp.get("total_drivers")))
        check("ac1_assigned", comp.get("assigned_drivers") == 16, str(comp.get("assigned_drivers")))
        check("ac1_unassigned", comp.get("unassigned_drivers") == 4, str(comp.get("unassigned_drivers")))
        snap = overview.get("compliance_snapshot", {})
        fin = overview.get("financial_snapshot", {})
        check("ac1_compliance_snapshot", bool(snap), "")
        check("ac1_financial_snapshot", fin.get("this_month_spend") is not None, "")
        check("ac1_recent_activity", len(overview.get("recent_activity", [])) <= 10, "")

        # AC 2 — truck 19 identity
        t19 = await get(client, "/api/trucks/19")
        check("ac2_unit", t19.get("unit_number") == 19, "")
        check("ac2_vin", "3HSDZAPR7GN145782" in str(t19.get("vin", "")), t19.get("vin", ""))
        check("ac2_price", float(t19.get("purchase_price") or 0) == 51000, str(t19.get("purchase_price")))

        # AC 3 — truck 6 assignment
        a6 = await get(client, "/api/trucks/6/assignment")
        cur = a6.get("current_driver") or {}
        check("ac3_driver", "Ramon" in str(cur.get("full_name", "")), cur.get("full_name", ""))
        check("ac3_code", cur.get("driver_code") == "D01", cur.get("driver_code", ""))

        # AC 4 — truck 19 maintenance
        m19 = await get(client, "/api/trucks/19/maintenance")
        check("ac4_events", m19.get("summary", {}).get("event_count", 0) > 0, "")
        check("ac4_spend", float(m19.get("summary", {}).get("total_spend", 0)) > 0, "")

        # AC 5 — compliance GWCA (any active truck)
        c19 = await get(client, "/api/trucks/19/compliance")
        ins = c19.get("categories", {}).get("insurance", {})
        check("ac5_policy", "GWCA" in str(ins.get("policy_number", "")), ins.get("policy_number", ""))
        check("ac5_insurer", "WEST" in str(ins.get("insurer", "")).upper() and "CASUALTY" in str(ins.get("insurer", "")).upper(), ins.get("insurer", ""))

        # AC 6 — financials TCO
        f19 = await get(client, "/api/trucks/19/financials")
        check("ac6_tco", float(f19.get("total_cost_of_ownership", 0)) > 0, "")

        # AC 7 — compliance matrix
        matrix = await get(client, "/api/compliance/matrix")
        check("ac7_rows", len(matrix.get("matrix", [])) == 16, str(len(matrix.get("matrix", []))))

        # AC 8 — fleet comparison
        cmp_resp = await get(client, "/api/fleet/comparison")
        check("ac8_trucks", len(cmp_resp.get("trucks", [])) >= 16, "")
        check("ac8_avg", cmp_resp.get("fleet_averages", {}).get("avg_tco") is not None, "")

        # AC 9 — vendors
        vendors = await get(client, "/api/vendors")
        check("ac9_vendors", len(vendors.get("vendors", [])) > 0, str(len(vendors.get("vendors", []))))

        # AC 10 — driver D03
        d03 = await get(client, "/api/drivers/D03")
        check("ac10_name", "Sergei" in str(d03.get("identity", {}).get("full_name", "")), "")
        assign = d03.get("current_assignment") or {}
        check("ac10_truck", assign.get("truck_unit") == 19, str(assign.get("truck_unit")))

        # AC 11 — truck graph
        g19 = await get(client, "/api/trucks/19/graph")
        check("ac11_nodes", len(g19.get("nodes", [])) > 0, "")
        check("ac11_center", g19.get("center_node") is not None, "")
        edge_types = {e.get("type") for e in g19.get("edges", [])}
        check("ac11_issued_by", "ISSUED_BY" in edge_types or any(
            n.get("type") == "InsurancePolicy" for n in g19.get("nodes", [])
        ), str(edge_types))

        # AC 12 — fleet graph
        fg = await get(client, "/api/fleet/graph")
        stats = fg.get("stats", {})
        check("ac12_trucks", stats.get("truck_count") == 20, str(stats.get("truck_count")))
        check("ac12_drivers", stats.get("driver_count") == 20, str(stats.get("driver_count")))

        # AC 13 — PDF file (first complete document)
        docs = await get(client, "/api/documents?limit=1&processing_status=complete")
        if docs.get("items"):
            doc_id = docs["items"][0]["id"]
            fr = await client.get(f"{BASE}/api/documents/{doc_id}/file")
            check("ac13_pdf", fr.status_code == 200 and "pdf" in fr.headers.get("content-type", "").lower(), fr.headers.get("content-type", ""))
        else:
            check("ac13_pdf", False, "no complete docs")

        # AC 14 — review queue
        rq = await get(client, "/api/documents/review")
        check("ac14_review", isinstance(rq.get("items"), list), "")

        # AC 15 — 404 on bad truck
        bad = await client.get(f"{BASE}/api/trucks/00000000-0000-0000-0000-000000000099")
        bad_body = bad.json() if bad.content else {}
        check("ac15_404", bad.status_code == 404, str(bad.status_code))
        check("ac15_code", bad_body.get("error_code") == "TRUCK_NOT_FOUND", bad_body.get("error_code", ""))

        # AC 16 — comparison perf
        t0 = time.perf_counter()
        await get(client, "/api/fleet/comparison")
        elapsed = time.perf_counter() - t0
        check("ac16_perf", elapsed < 3.0, f"{elapsed:.2f}s")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail and not ok else ""))

    print(f"\nPhase 3 acceptance: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
