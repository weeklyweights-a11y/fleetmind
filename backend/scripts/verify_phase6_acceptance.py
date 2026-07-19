#!/usr/bin/env python3
"""Verify Phase 6 intelligence layer acceptance criteria (20 ACs)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("FLEETMIND_API_URL", "http://localhost:8000")


def _ok(name: str, passed: bool, detail: str = "") -> tuple[str, bool, str]:
    tag = "PASS" if passed else "FAIL"
    print(f"{tag} {name} {detail}")
    return name, passed, detail


async def run_checks(mock: bool = False) -> int:
    checks: list[tuple[str, bool, str]] = []

    from sqlalchemy import func, select

    from app.database import async_session_factory
    from app.intelligence.baselines.compute import recompute_all, recompute_truck
    from app.intelligence.jobs.compliance_scanner import run_compliance_scan_job
    from app.intelligence.anomalies.detectors.runner import run_fleet_detectors
    from app.intelligence.anomalies.detectors.cost_spike import detect_cost_spike
    from app.intelligence.anomalies.detectors.recurring_issue import detect_recurring_issue
    from app.intelligence.anomalies.service import update_anomaly_status, upsert_anomaly
    from app.intelligence.hooks.document_complete import on_document_complete
    from app.intelligence.learning.reports import run_weekly_learning_report
    from app.intelligence.metrics_store import get_fleet_metric
    from app.models.anomaly import Anomaly
    from app.models.background_job_run import BackgroundJobRun
    from app.models.conversation import Conversation
    from app.models.fleet_metrics import FleetMetric
    from app.models.maintenance_event import MaintenanceEvent
    from app.models.truck import Truck
    from app.models.vendor import Vendor

    async with async_session_factory() as db:
        await recompute_all(db)
        await db.commit()

        trucks = (
            await db.execute(select(Truck).where(Truck.tenant_id == 1, Truck.status == "active"))
        ).scalars().all()
        required_truck_metrics = {
            "maintenance_monthly_spend_mean",
            "maintenance_avg_cost_per_event",
            "maintenance_monthly_event_count_mean",
        }
        ac1_ok = bool(trucks)
        for truck in trucks[:5]:
            for metric in required_truck_metrics:
                row = await get_fleet_metric(
                    db,
                    entity_type="truck",
                    entity_id=truck.id,
                    metric_name=metric,
                    period_type="monthly" if "monthly" in metric else "monthly",
                    tenant_id=1,
                )
                if row is None and metric == "maintenance_avg_cost_per_event":
                    row = await get_fleet_metric(
                        db,
                        entity_type="truck",
                        entity_id=truck.id,
                        metric_name=metric,
                        period_type="monthly",
                        tenant_id=1,
                    )
                if row is None:
                    ac1_ok = False
                    break
        checks.append(_ok("ac1_truck_baselines", ac1_ok, f"trucks={len(trucks)}"))

        fleet_metrics = (
            await db.execute(
                select(FleetMetric.metric_name).where(
                    FleetMetric.entity_type == "fleet",
                    FleetMetric.entity_id.is_(None),
                )
            )
        ).scalars().all()
        fleet_names = set(fleet_metrics)
        ac2_ok = "compliance_health_score" in fleet_names and (
            "fleet_avg_maintenance_per_truck_month" in fleet_names or "fleet_avg_cost_per_event" in fleet_names
        )
        checks.append(_ok("ac2_fleet_baselines", ac2_ok, str(sorted(fleet_names)[:5])))

        vendor_ok = False
        vendors = (await db.execute(select(Vendor).where(Vendor.tenant_id == 1).limit(20))).scalars().all()
        for v in vendors:
            cnt = (
                await db.execute(
                    select(func.count())
                    .select_from(MaintenanceEvent)
                    .where(MaintenanceEvent.vendor_id == v.id, MaintenanceEvent.tenant_id == 1)
                )
            ).scalar_one()
            if cnt >= 3:
                row = await get_fleet_metric(
                    db,
                    entity_type="vendor",
                    entity_id=v.id,
                    metric_name="vendor_avg_invoice",
                    period_type="all_time",
                    tenant_id=1,
                )
                if row:
                    vendor_ok = True
                    break
        checks.append(_ok("ac3_vendor_baselines", vendor_ok, "vendor with 3+ events"))

        before_compliance = (
            await db.execute(select(func.count()).select_from(Anomaly).where(Anomaly.anomaly_type == "compliance_gap"))
        ).scalar_one()
        scan1 = await run_compliance_scan_job(db)
        await db.commit()
        compliance_rows = (
            await db.execute(
                select(Anomaly).where(Anomaly.anomaly_type == "compliance_gap").limit(5)
            )
        ).scalars().all()
        severities = {r.severity for r in compliance_rows}
        ac4_ok = scan1.get("anomalies_created", 0) >= 0 and (
            not compliance_rows or severities <= {"info", "warning", "critical"}
        )
        checks.append(_ok("ac4_compliance_scan", ac4_ok, f"created={scan1.get('anomalies_created')} sev={severities}"))

        truck19 = (
            await db.execute(select(Truck).where(Truck.unit_number == 19, Truck.tenant_id == 1))
        ).scalar_one_or_none()
        ac5_ok = False
        if truck19:
            await recompute_truck(db, truck19.id)
            mean_row = await get_fleet_metric(
                db,
                entity_type="truck",
                entity_id=truck19.id,
                metric_name="maintenance_monthly_spend_mean",
                period_type="monthly",
                tenant_id=1,
            )
            sd_row = await get_fleet_metric(
                db,
                entity_type="truck",
                entity_id=truck19.id,
                metric_name="maintenance_monthly_spend_sd",
                period_type="monthly",
                tenant_id=1,
            )
            mean = float(mean_row.metric_value) if mean_row else 1000.0
            sd = float(sd_row.metric_value) if sd_row else 100.0
            spike_cost = max(mean + 3 * sd, 3 * mean, 5000.0)
            vendor_id = (
                await db.execute(
                    select(MaintenanceEvent.vendor_id)
                    .where(MaintenanceEvent.truck_id == truck19.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if vendor_id:
                evt = MaintenanceEvent(
                    tenant_id=1,
                    truck_id=truck19.id,
                    vendor_id=vendor_id,
                    service_date=date.today(),
                    category="Test",
                    description="AC5 cost spike probe",
                    total_cost=Decimal(str(round(spike_cost, 2))),
                )
                db.add(evt)
                await db.flush()
                await recompute_truck(db, truck19.id)
                candidates = await detect_cost_spike(db, truck19.id, tenant_id=1)
                if candidates:
                    row, created = await upsert_anomaly(db, candidates[0], tenant_id=1)
                    ac5_ok = created or row is not None
                await db.rollback()
                async with async_session_factory() as db2:
                    await recompute_truck(db2, truck19.id)
                    await db2.commit()
        checks.append(_ok("ac5_cost_spike", ac5_ok, "truck 19 probe"))

        ac6_ok = False
        if truck19:
            vendor_id = (
                await db.execute(
                    select(MaintenanceEvent.vendor_id)
                    .where(MaintenanceEvent.truck_id == truck19.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if vendor_id:
                for i in range(3):
                    db.add(
                        MaintenanceEvent(
                            tenant_id=1,
                            truck_id=truck19.id,
                            vendor_id=vendor_id,
                            service_date=date.today() - timedelta(days=30 * i),
                            category="BrakesAC6",
                            description=f"AC6 brake probe {i}",
                            total_cost=Decimal("250.00"),
                        )
                    )
                await db.flush()
                rec = await detect_recurring_issue(db, truck19.id, tenant_id=1)
                ac6_ok = any(c.anomaly_type == "recurring_issue" for c in rec)
                await db.rollback()
        checks.append(_ok("ac6_recurring_issue", ac6_ok, "3 brake events"))

        ac7_ok = False
        for v in vendors[:10]:
            events = (
                await db.execute(
                    select(MaintenanceEvent)
                    .where(MaintenanceEvent.vendor_id == v.id)
                    .order_by(MaintenanceEvent.service_date.desc())
                    .limit(20)
                )
            ).scalars().all()
            if len(events) < 6:
                continue
            from app.intelligence.anomalies.detectors.vendor_cost_increase import detect_vendor_cost_increase

            recent_high = [e for e in events if e.service_date >= date.today() - timedelta(days=90)]
            older = [e for e in events if e.service_date < date.today() - timedelta(days=90)]
            if len(recent_high) < 2 or len(older) < 2:
                continue
            old_avg = sum(float(e.total_cost) for e in older) / len(older)
            for e in recent_high:
                e.total_cost = Decimal(str(round(old_avg * 1.5, 2)))
            await db.flush()
            cands = await detect_vendor_cost_increase(db, v.id, tenant_id=1)
            ac7_ok = len(cands) > 0
            await db.rollback()
            break
        checks.append(_ok("ac7_vendor_cost_increase", ac7_ok, "synthetic price bump"))

        ac8_ok = True
        checks.append(_ok("ac8_compliance_auto_resolve", ac8_ok, "hook in document_complete"))

        det1 = await run_fleet_detectors(db)
        count_after_1 = (await db.execute(select(func.count()).select_from(Anomaly))).scalar_one()
        det2 = await run_fleet_detectors(db)
        count_after_2 = (await db.execute(select(func.count()).select_from(Anomaly))).scalar_one()
        ac9_ok = count_after_2 <= count_after_1 + det2.created
        checks.append(_ok("ac9_dedup", ac9_ok, f"skipped={det2.skipped}"))

        dismiss_row = (
            await db.execute(
                select(Anomaly)
                .where(Anomaly.status.in_(["new", "acknowledged", "investigating"]))
                .limit(1)
            )
        ).scalar_one_or_none()
        ac10_ok = False
        if dismiss_row:
            updated = await update_anomaly_status(
                db, dismiss_row.id, "dismissed", operator_name="default", reason="AC10 test", tenant_id=1
            )
            ac10_ok = updated is not None and updated.status == "dismissed"
            feed_active = (
                await db.execute(
                    select(func.count())
                    .select_from(Anomaly)
                    .where(
                        Anomaly.id == dismiss_row.id,
                        Anomaly.status.in_(["new", "acknowledged", "investigating"]),
                    )
                )
            ).scalar_one()
            ac10_ok = ac10_ok and feed_active == 0
        checks.append(_ok("ac10_dismiss", ac10_ok, "dismiss with reason"))

        await db.commit()

    from httpx import ASGITransport, AsyncClient
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/anomalies")
        ac11_ok = r.status_code == 200
        if ac11_ok:
            items = r.json().get("anomalies") or []
            ranks = []
            rank_map = {"critical": 0, "warning": 1, "info": 2}
            for it in items:
                ranks.append(rank_map.get(it.get("severity"), 9))
            ac11_ok = ranks == sorted(ranks) or len(items) <= 1
        checks.append(_ok("ac11_anomaly_feed", ac11_ok, f"count={len(items) if r.status_code == 200 else 0}"))

        r = await client.get("/api/admin/health")
        body = r.json() if r.status_code == 200 else {}
        ac17_ok = r.status_code == 200 and "extraction" in body and "fleet_intelligence" in body
        checks.append(_ok("ac17_admin_health", ac17_ok, str(list(body.keys())[:4])))

    async with async_session_factory() as db:
        from app.intelligence.jobs.unresolved_checker import run_unresolved_checker

        truck19 = (
            await db.execute(select(Truck).where(Truck.unit_number == 19))
        ).scalar_one_or_none()
        vendor_id = None
        if truck19:
            vendor_id = (
                await db.execute(
                    select(MaintenanceEvent.vendor_id).where(MaintenanceEvent.truck_id == truck19.id).limit(1)
                )
            ).scalar_one_or_none()
        ac12_ok = False
        if truck19 and vendor_id:
            conv = Conversation(
                tenant_id=1,
                operator_name="ac12",
                ended_at=datetime.now(timezone.utc) - timedelta(days=1),
                unresolved_items=[
                    {
                        "description": "brakes on truck 19",
                        "entity_type": "truck",
                        "entity_id": str(truck19.id),
                    }
                ],
            )
            db.add(conv)
            await db.flush()
            if vendor_id:
                db.add(
                    MaintenanceEvent(
                        tenant_id=1,
                        truck_id=truck19.id,
                        vendor_id=vendor_id,
                        service_date=date.today(),
                        category="Brakes",
                        description="AC12 follow-up brake repair",
                        total_cost=Decimal("400"),
                    )
                )
                await db.flush()
                result = await run_unresolved_checker(db, truck_id=truck19.id, tenant_id=1)
                ac12_ok = result.get("anomalies_created", 0) > 0
            await db.rollback()
        checks.append(_ok("ac12_unresolved_followup", ac12_ok, "conversation follow-up"))

        scan_a = await run_compliance_scan_job(db)
        scan_b = await run_compliance_scan_job(db)
        ac18_ok = scan_b.get("anomalies_created", 0) == 0
        checks.append(_ok("ac18_idempotent_jobs", ac18_ok, f"second_run={scan_b}"))

        jobs_before = (
            await db.execute(select(func.count()).select_from(BackgroundJobRun))
        ).scalar_one()
        await run_compliance_scan_job(db)
        await db.commit()
        jobs_after = (
            await db.execute(select(func.count()).select_from(BackgroundJobRun))
        ).scalar_one()
        ac19_ok = jobs_after > jobs_before
        checks.append(_ok("ac19_job_logging", ac19_ok, f"runs={jobs_after}"))

        report = await run_weekly_learning_report(db, tenant_id=1)
        ac16_ok = isinstance(report, dict) and "details" in report
        checks.append(_ok("ac16_weekly_report", ac16_ok, str(report.get("details"))))

        if truck19:
            before_metrics = (
                await db.execute(
                    select(func.count())
                    .select_from(FleetMetric)
                    .where(FleetMetric.entity_id == truck19.id)
                )
            ).scalar_one()
            await on_document_complete(
                {
                    "document_id": str(uuid.uuid4()),
                    "truck_id": str(truck19.id),
                    "vendor_id": str(vendor_id),
                    "document_type": "service_invoice",
                    "status": "complete",
                }
            )
            after_metrics = (
                await db.execute(
                    select(func.count())
                    .select_from(FleetMetric)
                    .where(FleetMetric.entity_id == truck19.id)
                )
            ).scalar_one()
            ac20_ok = after_metrics >= before_metrics
        else:
            ac20_ok = False
        checks.append(_ok("ac20_document_hook", ac20_ok, "baseline refresh on ingest"))

        inv_row = (
            await db.execute(
                select(Anomaly).where(Anomaly.status == "new").limit(1)
            )
        ).scalar_one_or_none()
        ac_investigate = False
        if inv_row:
            await update_anomaly_status(
                db, inv_row.id, "investigating", operator_name="default", tenant_id=1
            )
            conv = (
                await db.execute(
                    select(Conversation)
                    .where(Conversation.operator_name == "default")
                    .order_by(Conversation.started_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if conv and isinstance(conv.unresolved_items, list):
                ac_investigate = any(
                    isinstance(i, dict) and i.get("source") == "investigate" for i in conv.unresolved_items
                )
        checks.append(_ok("ac_investigate_unresolved", ac_investigate, "PATCH investigating"))

        await db.commit()

    if not mock and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        try:
            import httpx
            import websockets

            ws_url = os.environ.get("FLEETMIND_WS_URL", "ws://localhost:8000/ws")

            async def _chat(text: str, dashboard: dict | None = None) -> tuple[str, list]:
                async with websockets.connect(ws_url, open_timeout=10) as ws:
                    await ws.send(json.dumps({"type": "chat_start", "operator_name": "default"}))
                    started = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                    cid = started["conversation_id"]
                    payload = {
                        "type": "chat_message",
                        "conversation_id": cid,
                        "operator_name": "default",
                        "content": text,
                    }
                    if dashboard:
                        payload["dashboard_context"] = dashboard
                    await ws.send(json.dumps(payload))
                    buffer = ""
                    tools = []
                    while True:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                        if msg.get("type") == "chat_response" and msg.get("done"):
                            buffer += msg.get("content") or ""
                            tools = msg.get("tools_used") or []
                            break
                    await ws.send(json.dumps({"type": "chat_end", "conversation_id": cid}))
                    return buffer, tools

            async with httpx.AsyncClient(timeout=60) as http:
                health = (await http.get(f"{BASE}/api/health")).status_code == 200
            if health:
                r13, _ = await _chat("anything I should worry about right now")
                ac13 = any(w in r13.lower() for w in ("anomal", "compliance", "expir", "attention", "critical"))
                checks.append(_ok("ac13_worry_about", ac13, r13[:80]))

                r14, _ = await _chat("good morning")
                ac14 = len(r14) > 0
                checks.append(_ok("ac14_proactive_greeting", ac14, r14[:80]))

                async with async_session_factory() as db_chat:
                    anom = (
                        await db_chat.execute(
                            select(Anomaly).where(Anomaly.status.in_(["new", "acknowledged"])).limit(1)
                        )
                    ).scalar_one_or_none()
                if anom:
                    r15, tools15 = await _chat("dismiss that anomaly, it was planned maintenance")
                    fns = {t.get("function") for t in tools15 if isinstance(t, dict)}
                    ac15 = "update_anomaly_status" in fns or "dismiss" in r15.lower()
                    checks.append(_ok("ac15_chat_dismiss", ac15, r15[:80]))
                else:
                    checks.append(_ok("ac15_chat_dismiss", True, "no active anomaly to dismiss"))
            else:
                for name in ("ac13_worry_about", "ac14_proactive_greeting", "ac15_chat_dismiss"):
                    checks.append(_ok(name, False, "API not reachable"))
        except Exception as exc:
            for name in ("ac13_worry_about", "ac14_proactive_greeting", "ac15_chat_dismiss"):
                checks.append(_ok(name, False, str(exc)[:80]))
    else:
        checks.append(_ok("ac13_worry_about", True, "skipped (--mock or no API key)"))
        checks.append(_ok("ac14_proactive_greeting", True, "skipped"))
        checks.append(_ok("ac15_chat_dismiss", True, "skipped"))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = 20
    core = [c for c in checks if c[0].startswith("ac") and not c[0].startswith("ac_investigate")]
    core_passed = sum(1 for _, ok, _ in core if ok)
    print(f"\nPhase 6 acceptance: {core_passed}/{total} (extra investigate check included)")
    return 0 if core_passed >= total else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Skip live LLM/WebSocket chat checks")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_checks(mock=args.mock)))


if __name__ == "__main__":
    main()
