#!/usr/bin/env python3
"""Verify Phase 2 acceptance criteria for the 197-document Sunflower dataset."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.database import async_session_factory
from app.models.assignment import Assignment
from app.models.document import Document
from app.models.driver import Driver
from app.models.extraction_correction import ExtractionCorrection
from app.models.ifta import IFTAFiling, IFTAJurisdictionDetail, IFTAVehicleDetail
from app.models.insurance_coverage import InsuranceCoverage
from app.models.maintenance_event import MaintenanceEvent
from app.models.mileage_record import MileageRecord
from app.models.registration import Registration
from app.models.title import Title
from app.models.truck import Truck
from app.models.vendor import Vendor
from app.neo4j_client import get_neo4j_driver

# Counts for the 197-PDF Buildathon archive with inferred Unit 14 (no BOS in zip).
EXPECTED = {
    "documents": 197,
    "trucks": 20,
    "drivers": 20,
    "maintenance_events": 77,
    "insurance_coverages": 16,
    "registrations": 16,
    "titles": 20,
    "ifta_filings": 3,
    "assignments_min": 15,
    "complete_min": 197,
    "failed_max": 0,
}


async def count(model) -> int:
    async with async_session_factory() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    doc_total = await count(Document)
    trucks = await count(Truck)
    drivers = await count(Driver)
    maintenance = await count(MaintenanceEvent)
    insurance = await count(InsuranceCoverage)
    registrations = await count(Registration)
    titles = await count(Title)
    ifta = await count(IFTAFiling)
    ifta_j = await count(IFTAJurisdictionDetail)
    ifta_v = await count(IFTAVehicleDetail)
    assignments = await count(Assignment)

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
        failed = (
            await db.execute(
                select(func.count()).select_from(Document).where(Document.processing_status == "failed")
            )
        ).scalar_one()
        test_pdfs = (
            await db.execute(
                select(func.count()).select_from(Document).where(Document.original_filename == "test.pdf")
            )
        ).scalar_one()
        vins = (await db.execute(select(Truck.vin))).scalars().all()
        active = (
            await db.execute(
                select(func.count()).select_from(Truck).where(Truck.status == "active")
            )
        ).scalar_one()
        sold = (
            await db.execute(
                select(func.count()).select_from(Truck).where(Truck.status == "sold")
            )
        ).scalar_one()

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    check("documents", doc_total == EXPECTED["documents"], f"{doc_total}/{EXPECTED['documents']}")
    check("trucks", trucks == EXPECTED["trucks"], f"{trucks}/{EXPECTED['trucks']}")
    check("drivers", drivers == EXPECTED["drivers"], f"{drivers}/{EXPECTED['drivers']}")
    check("maintenance_events", maintenance == EXPECTED["maintenance_events"], f"{maintenance}/{EXPECTED['maintenance_events']}")
    check("insurance_coverages", insurance == EXPECTED["insurance_coverages"], f"{insurance}/{EXPECTED['insurance_coverages']}")
    check("registrations", registrations == EXPECTED["registrations"], f"{registrations}/{EXPECTED['registrations']}")
    check("titles", titles == EXPECTED["titles"], f"{titles}/{EXPECTED['titles']}")
    check("ifta_filings", ifta == EXPECTED["ifta_filings"], f"{ifta}/{EXPECTED['ifta_filings']}")
    check("ifta_jurisdiction_details", ifta_j >= EXPECTED["ifta_filings"], f"{ifta_j}")
    check("ifta_vehicle_details", ifta_v >= 1, f"{ifta_v}")
    check("assignments", assignments >= EXPECTED["assignments_min"], f"{assignments}")
    check("complete docs", complete >= EXPECTED["complete_min"], f"{complete} (review={review})")
    check("failed docs", failed <= EXPECTED["failed_max"], f"{failed}")
    check("no test.pdf", test_pdfs == 0, str(test_pdfs))
    check("VIN format (17 chars)", all(len(v) == 17 for v in vins if v), f"{len(vins)} trucks")
    check("trucks active", active >= 15, f"active={active} sold={sold}")

    neo = get_neo4j_driver()
    async with neo.session() as session:
        neo_trucks = await (await session.run("MATCH (t:Truck) RETURN count(t) AS c")).single()
        neo_drivers = await (await session.run("MATCH (d:Driver) RETURN count(d) AS c")).single()
    check("neo4j trucks", (neo_trucks["c"] if neo_trucks else 0) == EXPECTED["trucks"], str(neo_trucks))
    check("neo4j drivers", (neo_drivers["c"] if neo_drivers else 0) == EXPECTED["drivers"], str(neo_drivers))

    check("vendors", (await count(Vendor)) >= 1, "")
    check("mileage_records", (await count(MileageRecord)) >= 1, "")
    check("extraction_corrections", (await count(ExtractionCorrection)) >= 0, "")

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        suffix = f" ({detail})" if detail else ""
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{suffix}")

    print(f"\n{passed}/{len(checks)} checks passed")
    if passed < len(checks):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
