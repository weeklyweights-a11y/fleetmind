#!/usr/bin/env python3
"""Show extraction vs resolution gaps for documents marked complete without entities."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.database import async_session_factory
from app.enums import DocumentType
from app.models.document import Document
from app.models.document_normalized_record import DocumentNormalizedRecord

TRUCK_DEPENDENT = {
    DocumentType.SERVICE_INVOICE.value,
    DocumentType.INSURANCE_CARD.value,
    DocumentType.IRP_CAB_CARD.value,
    DocumentType.TITLE.value,
    DocumentType.FORM_2290.value,
}


async def main() -> None:
    async with async_session_factory() as db:
        docs = (
            await db.execute(
                select(Document).where(
                    Document.processing_status == "complete",
                    Document.truck_id.is_(None),
                    Document.document_type.in_(tuple(TRUCK_DEPENDENT)),
                )
            )
        ).scalars().all()

        print(f"Complete truck-dependent docs with truck_id=NULL: {len(docs)}")
        for doc in docs:
            notes = {}
            if doc.review_notes:
                try:
                    notes = json.loads(doc.review_notes)
                except json.JSONDecodeError:
                    notes = {"raw": doc.review_notes[:200]}
            extracted = notes.get("extracted_fields", {})
            unit = extracted.get("unit_number") or extracted.get("fleet_unit_no")
            vin = extracted.get("vin")
            print(
                f"  {doc.original_filename} type={doc.document_type} "
                f"unit={unit!r} vin={vin!r}"
            )

        ifta_candidates = (
            await db.execute(
                select(Document).where(
                    Document.original_filename.in_(
                        ("document_044.pdf", "document_045.pdf", "document_046.pdf")
                    )
                )
            )
        ).scalars().all()
        print(f"\nIFTA candidate docs: {len(ifta_candidates)}")
        for doc in ifta_candidates:
            junctions = (
                await db.execute(
                    select(DocumentNormalizedRecord).where(
                        DocumentNormalizedRecord.document_id == doc.id
                    )
                )
            ).scalars().all()
            tables = [j.target_table for j in junctions]
            print(f"  {doc.original_filename} type={doc.document_type} junctions={tables}")


if __name__ == "__main__":
    asyncio.run(main())
