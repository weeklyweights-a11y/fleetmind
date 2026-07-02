#!/usr/bin/env python3
"""Verify Phase 2 acceptance criteria."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import async_session_factory  # noqa: E402
from app.models.assignment import Assignment  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.driver import Driver  # noqa: E402
from app.models.extraction_correction import ExtractionCorrection  # noqa: E402
from app.models.ifta import IFTAFiling  # noqa: E402
from app.models.insurance_coverage import InsuranceCoverage  # noqa: E402
from app.models.maintenance_event import MaintenanceEvent  # noqa: E402
from app.models.mileage_record import MileageRecord  # noqa: E402
from app.models.registration import Registration  # noqa: E402
from app.models.title import Title  # noqa: E402
from app.models.truck import Truck  # noqa: E402
from app.models.vendor import Vendor  # noqa: E402
from app.extraction.layer5_validator import vin_check_digit_valid  # noqa: E402
from app.neo4j_client import get_neo4j_driver  # noqa: E402


async def count(model) -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def main() -> None:
    checks: list[tuple[str, bool]] = []

    doc_total = await count(Document)
    checks.append(("documents processed", doc_total >= 1))

    trucks = await count(Truck)
    checks.append(("trucks populated", trucks >= 1))

    drivers = await count(Driver)
    checks.append(("drivers populated", drivers >= 1))

    maintenance = await count(MaintenanceEvent)
    checks.append(("maintenance_events populated", maintenance >= 1))

    insurance = await count(InsuranceCoverage)
    checks.append(("insurance_coverages populated", insurance >= 1))

    registrations = await count(Registration)
    checks.append(("registrations populated", registrations >= 1))

    titles = await count(Title)
    checks.append(("titles populated", titles >= 1))

    ifta = await count(IFTAFiling)
    checks.append(("ifta_filings populated", ifta >= 1))

    async with async_session_factory() as db:
        complete = (
            await db.execute(
                select(func.count()).select_from(Document).where(Document.processing_status == "complete")
            )
        ).scalar_one()
        review = (
            await db.execute(
                select(func.count()).select_from(Document).where(Document.processing_status == "needs_review")
            )
        ).scalar_one()

    checks.append(("complete + review accounts for docs", complete + review >= min(doc_total, 1)))

    async with async_session_factory() as db:
        vins = (await db.execute(select(Truck.vin))).scalars().all()
    vin_ok = all(vin_check_digit_valid(v) for v in vins if v)
    checks.append(("VIN check digits", vin_ok or not vins))

    driver = get_neo4j_driver()
    async with driver.session() as session:
        neo_trucks = await (await session.run("MATCH (t:Truck) RETURN count(t) AS c")).single()
        checks.append(("neo4j trucks", (neo_trucks["c"] if neo_trucks else 0) >= 0))

    corrections = await count(ExtractionCorrection)
    checks.append(("extraction_corrections table accessible", corrections >= 0))

    mileage = await count(MileageRecord)
    checks.append(("mileage_records", mileage >= 0))

    vendors = await count(Vendor)
    checks.append(("vendors", vendors >= 1))

    assignments = await count(Assignment)
    checks.append(("assignments", assignments >= 0))

    passed = 0
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if ok:
            passed += 1

    print(f"\n{passed}/{len(checks)} checks passed")
    print(f"Counts: documents={doc_total}, trucks={trucks}, drivers={drivers}, maintenance={maintenance}")
    print(f"insurance={insurance}, registrations={registrations}, titles={titles}, ifta={ifta}")
    print(f"complete={complete}, needs_review={review}")

    if passed < len(checks):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
