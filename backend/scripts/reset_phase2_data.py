#!/usr/bin/env python3
"""Wipe Phase 2 extracted data and document uploads for a clean re-import."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import delete

from app.config import settings
from app.database import async_session_factory
from app.models.assignment import Assignment
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.driver import Driver
from app.models.emission_cert import EmissionCert
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
from app.redis_client import DOCUMENT_PROCESSING_DLQ, DOCUMENT_PROCESSING_QUEUE, get_redis


async def main() -> None:
    async with async_session_factory() as db:
        for model in [
            ExtractionCorrection,
            DocumentChunk,
            DocumentNormalizedRecord,
            MileageRecord,
            MaintenanceEvent,
            InsuranceCoverage,
            Registration,
            Title,
            Assignment,
            IFTAVehicleDetail,
            IFTAJurisdictionDetail,
            IFTAFiling,
            EmissionCert,
            Document,
            Truck,
            Driver,
            Vendor,
        ]:
            await db.execute(delete(model))
        await db.commit()
    print("Postgres extraction tables cleared")

    storage = Path(settings.document_storage_path)
    if storage.exists():
        for pdf in storage.glob("*.pdf"):
            pdf.unlink()
        print(f"Cleared uploaded PDFs from {storage}")

    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    print("Neo4j graph cleared")

    redis = get_redis()
    await redis.delete(DOCUMENT_PROCESSING_QUEUE)
    await redis.delete(DOCUMENT_PROCESSING_DLQ)
    print("Redis queues cleared")


if __name__ == "__main__":
    asyncio.run(main())
