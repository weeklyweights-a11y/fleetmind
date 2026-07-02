"""Extraction pipeline orchestrator."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.enums import DocumentType, ProcessingStatus
from app.extraction import layer7_enricher
from app.extraction.classifier import classify_document
from app.extraction import graph_writer
from app.extraction.layer1_reader import read_document
from app.extraction.layer2_layout import build_layout
from app.extraction.layer3_extractor import extract_fields
from app.extraction.layer4_normalizer import normalize_fields
from app.extraction.layer5_validator import validate_fields
from app.extraction.layer6_corrector import correct_fields
from app.extraction.types import PipelineContext
from app.models.document import Document
from app.services.extraction_status import update_status

logger = logging.getLogger(__name__)


async def _sync_neo4j(ctx: PipelineContext) -> None:
    if not ctx.extraction:
        return
    fields = ctx.normalized_fields
    doc_id = uuid.UUID(ctx.document_id)
    dtype = ctx.extraction.document_type
    tenant_id = ctx.tenant_id

    if dtype == DocumentType.BILL_OF_SALE_PURCHASE.value and ctx.truck_id and ctx.vendor_id:
        await graph_writer.write_with_retry(
            graph_writer.write_purchase,
            uuid.UUID(ctx.truck_id),
            uuid.UUID(ctx.vendor_id),
            doc_id,
            {**fields, "unit_number": fields.get("fleet_unit_no")},
            tenant_id,
        )
    elif dtype == DocumentType.BILL_OF_SALE_SALE.value and ctx.truck_id and ctx.vendor_id:
        await graph_writer.write_with_retry(
            graph_writer.write_sale,
            uuid.UUID(ctx.truck_id),
            uuid.UUID(ctx.vendor_id),
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.CDL.value and ctx.driver_id:
        await graph_writer.write_with_retry(
            graph_writer.write_cdl,
            uuid.UUID(ctx.driver_id),
            uuid.UUID(ctx.truck_id) if ctx.truck_id else None,
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.SERVICE_INVOICE.value and ctx.truck_id and ctx.vendor_id:
        await graph_writer.write_with_retry(
            graph_writer.write_maintenance,
            uuid.UUID(ctx.truck_id),
            uuid.UUID(ctx.vendor_id),
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.INSURANCE_CARD.value and ctx.truck_id and ctx.insurance_coverage_id:
        await graph_writer.write_with_retry(
            graph_writer.write_insurance,
            uuid.UUID(ctx.truck_id),
            uuid.UUID(ctx.insurance_coverage_id),
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.IRP_CAB_CARD.value and ctx.truck_id:
        await graph_writer.write_with_retry(
            graph_writer.write_registration,
            uuid.UUID(ctx.truck_id),
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.TITLE.value and ctx.truck_id:
        await graph_writer.write_with_retry(
            graph_writer.write_title,
            uuid.UUID(ctx.truck_id),
            doc_id,
            fields,
            tenant_id,
        )
    elif dtype == DocumentType.IFTA_FILING.value and ctx.ifta_filing_id:
        await graph_writer.write_with_retry(
            graph_writer.write_ifta,
            uuid.UUID(ctx.ifta_filing_id),
            doc_id,
            fields,
            ctx.ifta_vehicle_graph,
            tenant_id,
        )
    elif dtype not in (DocumentType.UNKNOWN.value,) and ctx.truck_id:
        await graph_writer.write_with_retry(
            graph_writer.merge_document,
            doc_id,
            dtype,
            fields.get("document_number") or fields.get("invoice_number"),
            fields.get("document_date") or fields.get("invoice_date"),
            tenant_id,
        )
        await graph_writer.write_with_retry(graph_writer.link_has_document, uuid.UUID(ctx.truck_id), doc_id)


async def run(document_id: str, file_path: str, tenant_id: int = 1) -> None:
    ctx = PipelineContext(
        document_id=document_id,
        file_path=file_path,
        original_filename=file_path,
        tenant_id=tenant_id,
    )

    async with async_session_factory() as db:
        doc_uuid = uuid.UUID(document_id)
        result = await db.execute(select(Document).where(Document.id == doc_uuid))
        doc = result.scalar_one_or_none()
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        ctx.original_filename = doc.original_filename

        try:
            await update_status(db, doc_uuid, ProcessingStatus.PARSING)
            ctx.l1 = read_document(file_path)
            await db.commit()

            ctx.l2 = build_layout(ctx.l1)
            doc_type = classify_document(ctx.l1, ctx.l2, file_path=doc.file_path)

            await update_status(db, doc_uuid, ProcessingStatus.EXTRACTING)
            ctx.extraction = await extract_fields(doc_type, ctx.l1, ctx.l2)
            await db.commit()

            await update_status(db, doc_uuid, ProcessingStatus.NORMALIZING)
            ctx.normalized_fields, ctx.normalization_issues = normalize_fields(
                ctx.extraction.extracted_fields
            )
            await db.commit()

            await update_status(db, doc_uuid, ProcessingStatus.VALIDATING)
            ctx.validation = validate_fields(
                ctx.extraction.document_type,
                ctx.normalized_fields,
                ctx.extraction.field_confidences,
                ctx.l1.parse_confidence,
            )

            corrections = []
            if ctx.validation.failed_fields and settings.gemini_api_key:
                ctx.normalized_fields, ctx.l6_attempts = await correct_fields(
                    ctx.extraction.document_type,
                    ctx.normalized_fields,
                    ctx.validation,
                    ctx.extraction.field_confidences,
                    ctx.l1.full_text[:3000],
                    ctx.l1.parse_confidence,
                )
                ctx.validation = validate_fields(
                    ctx.extraction.document_type,
                    ctx.normalized_fields,
                    ctx.extraction.field_confidences,
                    ctx.l1.parse_confidence,
                )
                corrections = [a for a in ctx.l6_attempts if a.accepted]

            ctx.entity_resolution_confidence = ctx.validation.overall_confidence
            await layer7_enricher.enrich(db, ctx, corrections=corrections)

            try:
                await _sync_neo4j(ctx)
            except Exception as neo_exc:
                async with async_session_factory() as err_db:
                    result = await err_db.execute(select(Document).where(Document.id == doc_uuid))
                    err_doc = result.scalar_one()
                    err_doc.processing_status = ProcessingStatus.FAILED.value
                    err_doc.error_details = json.dumps(
                        {
                            "pg_committed": True,
                            "neo4j_error": str(neo_exc),
                            "repair_hint": f"graph_writer.repair_document_graph('{document_id}')",
                        }
                    )
                    await err_db.commit()
                raise

            needs_review = (
                bool(ctx.validation.failed_fields)
                or ctx.extraction.document_type == DocumentType.UNKNOWN.value
                or bool(ctx.resolution_issues)
                or not ctx.normalized_record_ids
            )
            final_status = (
                ProcessingStatus.NEEDS_REVIEW if needs_review else ProcessingStatus.COMPLETE
            )
            await update_status(
                db,
                doc_uuid,
                final_status,
                {
                    "document_type": ctx.extraction.document_type,
                    "truck_id": ctx.truck_id,
                    "driver_id": ctx.driver_id,
                    "vendor_id": ctx.vendor_id,
                    "affected_tables": ctx.affected_tables,
                },
            )
            await db.commit()

        except Exception as exc:
            logger.exception("Pipeline failed for %s", document_id)
            await db.rollback()
            async with async_session_factory() as err_db:
                result = await err_db.execute(select(Document).where(Document.id == doc_uuid))
                err_doc = result.scalar_one_or_none()
                if err_doc:
                    err_doc.processing_status = ProcessingStatus.FAILED.value
                    err_doc.error_details = str(exc)
                    await err_db.commit()
            raise
