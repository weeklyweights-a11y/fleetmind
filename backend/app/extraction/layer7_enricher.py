"""Layer 7: Write to Postgres, Neo4j, and chunks."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import DocumentType, ProcessingStatus, TruckStatus
from app.extraction import entity_resolver
from app.extraction.types import PipelineContext
from app.models.assignment import Assignment
from app.models.document import Document
from app.models.document_normalized_record import DocumentNormalizedRecord
from app.models.driver import Driver
from app.models.extraction_correction import ExtractionCorrection
from app.models.emission_cert import EmissionCert
from app.models.ifta import IFTAFiling, IFTAJurisdictionDetail, IFTAVehicleDetail
from app.models.insurance_coverage import InsuranceCoverage
from app.models.maintenance_event import MaintenanceEvent
from app.models.mileage_record import MileageRecord
from app.models.registration import Registration
from app.models.title import Title
from app.models.truck import Truck
from app.services.embeddings import store_chunks

logger = logging.getLogger(__name__)


def _flag_resolution_failure(ctx: PipelineContext, message: str) -> None:
    ctx.resolution_issues.append(message)
    if ctx.validation:
        ctx.validation.needs_review = True


async def _resolve_truck_or_flag(
    db: AsyncSession,
    ctx: PipelineContext,
    fields: dict[str, Any],
    doc_type: str,
) -> Truck | None:
    truck, _, inferred = await entity_resolver.resolve_truck(
        db,
        fields,
        doc_type,
        ctx.tenant_id,
        for_update=True,
        allow_infer=True,
    )
    if truck and inferred:
        ctx.inference_notes.append(
            f"Inferred truck unit {truck.unit_number} (VIN {truck.vin}) — no Bill of Sale on file"
        )
        ctx.affected_tables.append("trucks")
        await _record_junction(ctx, db, "trucks", truck.id)
    if not truck:
        unit = fields.get("unit_number") or fields.get("fleet_unit_no")
        vin = fields.get("vin")
        _flag_resolution_failure(
            ctx,
            f"Could not resolve truck — unit {unit!r}, VIN {vin!r} not found in trucks table",
        )
    return truck


def _needs_review(ctx: PipelineContext, doc_type: str) -> bool:
    if doc_type == DocumentType.UNKNOWN.value:
        return True
    if ctx.validation and ctx.validation.failed_fields:
        return True
    if ctx.resolution_issues:
        return True
    return not ctx.normalized_record_ids


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    cleaned = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    m = re.search(r"-?[\d,]+", str(value).replace(" ", ""))
    if not m:
        return None
    try:
        return int(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _review_notes(ctx: PipelineContext) -> str | None:
    if ctx.validation and not ctx.validation.needs_review and ctx.validation.overall_confidence >= 0.7:
        return None
    payload = {
        "extracted_fields": ctx.extraction.extracted_fields if ctx.extraction else {},
        "field_confidences": ctx.extraction.field_confidences if ctx.extraction else {},
        "validation_results": [
            {
                "field": k,
                "check_type": v.check_type,
                "expected": v.expected,
                "actual": v.actual,
            }
            for k, v in (ctx.validation.field_results.items() if ctx.validation else {})
        ],
        "l6_attempts": [
            {"field": a.field, "original": a.original, "proposed": a.proposed, "accepted": a.accepted}
            for a in ctx.l6_attempts
        ],
        "normalized_record_ids": ctx.normalized_record_ids,
        "fields_needing_attention": ctx.validation.failed_fields if ctx.validation else [],
        "resolution_issues": ctx.resolution_issues,
        "inference_notes": ctx.inference_notes,
    }
    return json.dumps(payload)


async def _junction(
    db: AsyncSession,
    document_id: uuid.UUID,
    table: str,
    record_id: uuid.UUID,
    confidence: float | None,
    tenant_id: int,
) -> None:
    db.add(
        DocumentNormalizedRecord(
            document_id=document_id,
            target_table=table,
            target_record_id=record_id,
            extraction_confidence=confidence,
            tenant_id=tenant_id,
        )
    )


async def _record_junction(
    ctx: PipelineContext,
    db: AsyncSession,
    table: str,
    record_id: uuid.UUID,
    confidence: float | None = None,
) -> None:
    await _junction(db, uuid.UUID(ctx.document_id), table, record_id, confidence, ctx.tenant_id)
    ctx.normalized_record_ids.append({"table": table, "id": str(record_id)})


async def _write_bos_purchase(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    existing, _, _ = await entity_resolver.resolve_truck(
        db, fields, DocumentType.BILL_OF_SALE_PURCHASE.value, ctx.tenant_id, for_update=True
    )
    seller_name = fields.get("seller_name", "Unknown Seller")
    seller, _ = await entity_resolver.resolve_vendor(db, seller_name, None, "seller", ctx.tenant_id)

    if existing:
        truck = existing
        truck.year = int(fields.get("year", truck.year))
        truck.make = str(fields.get("make", truck.make))
        truck.model = str(fields.get("model", truck.model))
        truck.body_type = fields.get("body_type") or truck.body_type
        truck.color = fields.get("color") or truck.color
        truck.acquired_date = fields.get("document_date") or truck.acquired_date
        truck.purchase_price = fields.get("purchase_price") or truck.purchase_price
        truck.acquired_from_vendor_id = seller.id
        truck.initial_odometer = fields.get("odometer") or truck.initial_odometer
        truck.status = TruckStatus.ACTIVE.value
    else:
        truck = Truck(
            id=uuid.uuid4(),
            unit_number=int(fields["fleet_unit_no"]),
            vin=str(fields["vin"]),
            year=int(fields["year"]),
            make=str(fields.get("make", "Unknown")),
            model=str(fields.get("model", "Unknown")),
            body_type=fields.get("body_type"),
            color=fields.get("color"),
            status=TruckStatus.ACTIVE.value,
            acquired_date=fields.get("document_date"),
            purchase_price=fields.get("purchase_price"),
            acquired_from_vendor_id=seller.id,
            initial_odometer=fields.get("odometer"),
            tenant_id=ctx.tenant_id,
        )
        db.add(truck)
    await db.flush()
    ctx.truck_id = str(truck.id)
    ctx.vendor_id = str(seller.id)
    ctx.affected_tables.extend(["trucks", "vendors"])

    if fields.get("odometer"):
        mr = MileageRecord(
            truck_id=truck.id,
            record_date=fields.get("document_date") or date.today(),
            odometer_reading=int(fields["odometer"]),
            source_type="bill_of_sale_purchase",
            source_document_id=uuid.UUID(ctx.document_id),
            tenant_id=ctx.tenant_id,
        )
        db.add(mr)
        await db.flush()
        await _record_junction(ctx, db, "mileage_records", mr.id)
        ctx.affected_tables.append("mileage_records")

    await _record_junction(ctx, db, "trucks", truck.id)
    await _record_junction(ctx, db, "vendors", seller.id)


async def _write_bos_sale(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    truck, conf, _ = await entity_resolver.resolve_truck(
        db, fields, DocumentType.BILL_OF_SALE_SALE.value, ctx.tenant_id, for_update=True
    )
    if not truck:
        _flag_resolution_failure(
            ctx,
            f"Could not resolve truck for sale — unit {fields.get('fleet_unit_no')!r}, "
            f"VIN {fields.get('vin')!r} not found",
        )
        return
    truck.status = TruckStatus.SOLD.value
    truck.disposed_date = fields.get("document_date")
    truck.sale_price = fields.get("purchase_price") or fields.get("sale_price")
    truck.disposed_to = fields.get("buyer_name")
    truck.disposal_type = "sold"
    ctx.truck_id = str(truck.id)

    buyer, _ = await entity_resolver.resolve_vendor(
        db, str(fields.get("buyer_name", "Buyer")), None, "buyer", ctx.tenant_id
    )
    ctx.vendor_id = str(buyer.id)

    active = (
        await db.execute(
            select(Assignment).where(
                Assignment.truck_id == truck.id,
                Assignment.end_date.is_(None),
            )
        )
    ).scalars().all()
    for a in active:
        a.end_date = fields.get("document_date")

    await _record_junction(ctx, db, "trucks", truck.id)
    ctx.affected_tables.append("trucks")


async def _write_cdl(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    driver, _, create = await entity_resolver.resolve_driver(
        db, fields, DocumentType.CDL.value, ctx.tenant_id
    )
    if create or driver is None:
        first = fields.get("first_name", "")
        last = fields.get("last_name", "")
        full = fields.get("full_name") or f"{first} {last}".strip()
        driver = Driver(
            id=uuid.uuid4(),
            driver_code=fields.get("driver_code"),
            first_name=str(first or full.split()[0] if full else "Unknown"),
            last_name=str(last or (full.split()[-1] if full and " " in full else "")),
            full_name=str(full or "Unknown"),
            license_number=str(fields.get("license_number", "UNKNOWN")),
            license_class=str(fields.get("license_class", "A")),
            license_issue_date=fields.get("license_issue_date"),
            license_expiry_date=fields.get("license_expiry_date") or date.today(),
            license_endorsements=fields.get("endorsements"),
            license_restrictions=fields.get("restrictions"),
            date_of_birth=fields.get("date_of_birth"),
            address=fields.get("address"),
            sex=fields.get("sex"),
            height=fields.get("height"),
            weight_lbs=fields.get("weight"),
            eye_color=fields.get("eye_color"),
            tenant_id=ctx.tenant_id,
        )
        db.add(driver)
        await db.flush()
    ctx.driver_id = str(driver.id)
    await _record_junction(ctx, db, "drivers", driver.id)
    ctx.affected_tables.append("drivers")

    fleet = fields.get("fleet_unit_assignment")
    if fleet is not None and str(fleet).lower() != "none":
        truck, _, _ = await entity_resolver.resolve_truck(
            db,
            {"unit_number": fleet},
            DocumentType.CDL.value,
            ctx.tenant_id,
            for_update=True,
            allow_infer=False,
        )
        if truck:
            active = (
                await db.execute(
                    select(Assignment).where(
                        Assignment.truck_id == truck.id,
                        Assignment.end_date.is_(None),
                    )
                )
            ).scalars().all()
            for a in active:
                if a.driver_id != driver.id:
                    a.end_date = fields.get("license_issue_date") or date.today()
            db.add(
                Assignment(
                    truck_id=truck.id,
                    driver_id=driver.id,
                    start_date=fields.get("license_issue_date") or date.today(),
                    assignment_type="primary",
                    source_document_id=uuid.UUID(ctx.document_id),
                    tenant_id=ctx.tenant_id,
                )
            )
            await db.flush()
            assignment = (
                await db.execute(
                    select(Assignment).where(
                        Assignment.truck_id == truck.id,
                        Assignment.driver_id == driver.id,
                        Assignment.end_date.is_(None),
                    ).limit(1)
                )
            ).scalars().first()
            ctx.truck_id = str(truck.id)
            if assignment:
                await _record_junction(ctx, db, "assignments", assignment.id)
        else:
            _flag_resolution_failure(
                ctx,
                f"Could not resolve truck for CDL assignment — unit {fleet!r} not found",
            )


async def _write_invoice(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    existing = (
        await db.execute(
            select(MaintenanceEvent).where(
                MaintenanceEvent.invoice_number == str(fields.get("invoice_number")),
                MaintenanceEvent.tenant_id == ctx.tenant_id,
            ).limit(1)
        )
    ).scalars().first()
    if existing:
        ctx.truck_id = str(existing.truck_id)
        ctx.vendor_id = str(existing.vendor_id)
        ctx.affected_tables.append("maintenance_events")
        await _record_junction(ctx, db, "maintenance_events", existing.id)
        return

    truck = await _resolve_truck_or_flag(db, ctx, fields, DocumentType.SERVICE_INVOICE.value)
    if not truck:
        return

    vendor_name = str(fields.get("vendor_name", "Unknown Vendor"))
    vendor, _ = await entity_resolver.resolve_vendor(db, vendor_name, None, "service", ctx.tenant_id)

    desc = f"Service invoice {fields.get('invoice_number', '')} - {fields.get('category', '')}"
    event = MaintenanceEvent(
        truck_id=truck.id,
        vendor_id=vendor.id,
        service_date=fields.get("invoice_date") or date.today(),
        category=str(fields.get("category", "General")),
        description=desc,
        parts_cost=fields.get("subtotal"),
        labor_cost=fields.get("labor_cost"),
        total_cost=fields.get("total") or Decimal("0"),
        sales_tax=fields.get("sales_tax"),
        payment_status=str(fields.get("payment_status", "unknown")),
        payment_method=fields.get("payment_method"),
        technician_name=fields.get("technician"),
        invoice_number=str(fields.get("invoice_number", "UNKNOWN")),
        po_number=fields.get("po_number"),
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(event)
    await db.flush()
    ctx.truck_id = str(truck.id)
    ctx.vendor_id = str(vendor.id)
    ctx.affected_tables.extend(["maintenance_events", "vendors"])
    await _record_junction(ctx, db, "maintenance_events", event.id)


async def _write_insurance(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    truck = await _resolve_truck_or_flag(db, ctx, fields, DocumentType.INSURANCE_CARD.value)
    if not truck:
        return
    policy = str(fields.get("policy_number", "GWCA-KS-77 04188"))
    existing = (
        await db.execute(
            select(InsuranceCoverage).where(
                InsuranceCoverage.truck_id == truck.id,
                InsuranceCoverage.policy_number == policy,
                InsuranceCoverage.tenant_id == ctx.tenant_id,
            ).limit(1)
        )
    ).scalars().first()
    if existing:
        ctx.truck_id = str(truck.id)
        ctx.insurance_coverage_id = str(existing.id)
        await _record_junction(ctx, db, "insurance_coverages", existing.id)
        return
    insurer, _ = await entity_resolver.resolve_vendor(
        db, str(fields.get("insurer_name", "Great West Casualty Company")),
        None,
        "insurance_company",
        ctx.tenant_id,
    )
    cov = InsuranceCoverage(
        truck_id=truck.id,
        policy_number=str(fields.get("policy_number", "GWCA-KS-77 04188")),
        insurer_name=str(fields.get("insurer_name", insurer.name)),
        insurer_vendor_id=insurer.id,
        agent_name=fields.get("agent_name"),
        coverage_type=str(fields.get("coverage_type", "Liability")),
        liability_limit=fields.get("liability_limit"),
        cargo_limit=fields.get("cargo_limit"),
        effective_date=fields.get("effective_date") or date.today(),
        expiry_date=fields.get("expiry_date") or date.today(),
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(cov)
    await db.flush()
    ctx.truck_id = str(truck.id)
    ctx.insurance_coverage_id = str(cov.id)
    ctx.affected_tables.append("insurance_coverages")
    await _record_junction(ctx, db, "insurance_coverages", cov.id)


async def _write_irp(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    truck = await _resolve_truck_or_flag(db, ctx, fields, DocumentType.IRP_CAB_CARD.value)
    if not truck:
        return
    plate = fields.get("plate_number")
    existing = (
        await db.execute(
            select(Registration).where(
                Registration.truck_id == truck.id,
                Registration.registration_type == "irp",
                Registration.plate_number == plate,
                Registration.tenant_id == ctx.tenant_id,
            ).limit(1)
        )
    ).scalars().first()
    if existing:
        ctx.truck_id = str(truck.id)
        await _record_junction(ctx, db, "registrations", existing.id)
        return
    reg = Registration(
        truck_id=truck.id,
        registration_type="irp",
        state="KS",
        plate_number=fields.get("plate_number"),
        effective_date=fields.get("effective_date") or date.today(),
        expiry_date=fields.get("expiry_date") or date.today(),
        registered_weight=fields.get("registered_weight"),
        registration_fee=fields.get("registration_fee"),
        property_tax=fields.get("property_tax"),
        irp_apportioned_fee=fields.get("irp_apportioned_fee"),
        title_fee=fields.get("title_fee"),
        total_fees_paid=fields.get("total_fees"),
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(reg)
    await db.flush()
    ctx.truck_id = str(truck.id)
    ctx.affected_tables.append("registrations")
    await _record_junction(ctx, db, "registrations", reg.id)


async def _write_title(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    truck = await _resolve_truck_or_flag(db, ctx, fields, DocumentType.TITLE.value)
    if not truck:
        return

    if fields.get("year"):
        truck.year = int(fields["year"])
    if fields.get("make"):
        truck.make = str(fields["make"])
    if fields.get("model"):
        truck.model = str(fields["model"])
    if fields.get("color"):
        truck.color = str(fields["color"])
    ctx.truck_id = str(truck.id)

    title_no = str(fields.get("title_number", "UNKNOWN"))
    existing_title = (
        await db.execute(
            select(Title).where(
                Title.truck_id == truck.id,
                Title.title_number == title_no,
                Title.tenant_id == ctx.tenant_id,
            ).limit(1)
        )
    ).scalars().first()
    if existing_title:
        ctx.truck_id = str(truck.id)
        await _record_junction(ctx, db, "titles", existing_title.id)
        return

    title = Title(
        truck_id=truck.id,
        title_number=str(fields.get("title_number", "UNKNOWN")),
        title_state="KS",
        issue_date=fields.get("issue_date") or date.today(),
        vin=str(fields.get("vin", truck.vin)),
        owner_name=str(fields.get("owner_name", "Sunflower Freight Lines LLC")),
        owner_address=fields.get("owner_address"),
        lien_holder=fields.get("lien_holder"),
        title_fee=fields.get("title_fee"),
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(title)
    await db.flush()
    ctx.affected_tables.append("titles")
    await _record_junction(ctx, db, "titles", title.id)

    if fields.get("odometer"):
        mr = MileageRecord(
            truck_id=truck.id,
            record_date=fields.get("issue_date") or date.today(),
            odometer_reading=int(fields["odometer"]),
            source_type="title",
            source_document_id=uuid.UUID(ctx.document_id),
            tenant_id=ctx.tenant_id,
        )
        db.add(mr)
        await db.flush()
        await _record_junction(ctx, db, "mileage_records", mr.id)


async def _write_ifta(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    quarter = str(fields.get("quarter", "2025Q1"))
    existing = (
        await db.execute(
            select(IFTAFiling).where(
                IFTAFiling.tenant_id == ctx.tenant_id,
                IFTAFiling.quarter == quarter,
            ).limit(1)
        )
    ).scalars().first()
    if existing:
        ctx.affected_tables.append("ifta_filings")
        await _record_junction(ctx, db, "ifta_filings", existing.id)
        return

    mpg = fields.get("average_fleet_mpg")
    if mpg is None and fields.get("total_miles") and fields.get("total_gallons"):
        try:
            mpg = Decimal(str(fields["total_miles"])) / Decimal(str(fields["total_gallons"]))
        except (ArithmeticError, ValueError):
            mpg = None

    filing = IFTAFiling(
        id=uuid.uuid4(),
        ifta_account_number=str(fields.get("ifta_account", "UNKNOWN")),
        quarter=quarter,
        filing_date=fields.get("filing_date") or date.today(),
        total_fleet_miles=fields.get("total_miles"),
        total_fleet_gallons=fields.get("total_gallons"),
        total_tax_due=fields.get("total_tax_due"),
        balance_due=fields.get("balance_due"),
        average_fleet_mpg=mpg,
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(filing)
    await db.flush()
    ctx.ifta_filing_id = str(filing.id)
    ctx.affected_tables.append("ifta_filings")
    await _record_junction(ctx, db, "ifta_filings", filing.id)

    raw_jurisdictions = fields.get("jurisdiction_details") or []
    if isinstance(raw_jurisdictions, list):
        for row in raw_jurisdictions:
            if not isinstance(row, dict):
                continue
            db.add(
                IFTAJurisdictionDetail(
                    filing_id=filing.id,
                    jurisdiction=str(row.get("jurisdiction", "UNK")),
                    miles=_to_int(row.get("miles")),
                    gallons=_to_decimal(row.get("gallons")),
                    taxable_gallons=_to_decimal(row.get("taxable_gallons")),
                    tax_rate=_to_decimal(row.get("tax_rate")),
                    tax_due=_to_decimal(row.get("tax_due")),
                    tenant_id=ctx.tenant_id,
                )
            )
        if raw_jurisdictions:
            ctx.affected_tables.append("ifta_jurisdiction_details")

    raw_vehicles = fields.get("vehicle_details") or []
    if isinstance(raw_vehicles, list):
        for row in raw_vehicles:
            if not isinstance(row, dict) or not row.get("vin"):
                continue
            truck, _, _ = await entity_resolver.resolve_truck(
                db, {"vin": row["vin"]}, DocumentType.IFTA_FILING.value, ctx.tenant_id
            )
            db.add(
                IFTAVehicleDetail(
                    filing_id=filing.id,
                    truck_id=truck.id if truck else None,
                    vin=str(row["vin"]),
                    miles=int(str(row.get("miles", "0")).replace(",", "") or 0) or None,
                    gallons=int(str(row.get("gallons", "0")).replace(",", "") or 0) or None,
                    tenant_id=ctx.tenant_id,
                )
            )
            if truck:
                ctx.ifta_vehicle_graph.append(
                    {
                        "truck_pg_id": str(truck.id),
                        "miles": int(str(row.get("miles", "0")).replace(",", "") or 0) or None,
                        "gallons": int(str(row.get("gallons", "0")).replace(",", "") or 0) or None,
                    }
                )
        if raw_vehicles:
            ctx.affected_tables.append("ifta_vehicle_details")
    await db.flush()


async def _write_form_2290(db: AsyncSession, ctx: PipelineContext, fields: dict[str, Any]) -> None:
    truck = await _resolve_truck_or_flag(db, ctx, fields, DocumentType.FORM_2290.value)
    if not truck:
        return
    ctx.truck_id = str(truck.id)
    cert = EmissionCert(
        truck_id=truck.id,
        test_date=fields.get("document_date") or date.today(),
        result="filed",
        certificate_number=fields.get("document_number"),
        source_document_id=uuid.UUID(ctx.document_id),
        tenant_id=ctx.tenant_id,
    )
    db.add(cert)
    await db.flush()
    ctx.affected_tables.append("emission_certs")
    await _record_junction(ctx, db, "emission_certs", cert.id)


async def enrich(
    db: AsyncSession,
    ctx: PipelineContext,
    corrections: list[Any] | None = None,
) -> None:
    fields = ctx.normalized_fields
    doc_type = ctx.extraction.document_type if ctx.extraction else "unknown"

    if doc_type == DocumentType.BILL_OF_SALE_PURCHASE.value:
        await _write_bos_purchase(db, ctx, fields)
    elif doc_type == DocumentType.BILL_OF_SALE_SALE.value:
        await _write_bos_sale(db, ctx, fields)
    elif doc_type == DocumentType.CDL.value:
        await _write_cdl(db, ctx, fields)
    elif doc_type == DocumentType.SERVICE_INVOICE.value:
        await _write_invoice(db, ctx, fields)
    elif doc_type == DocumentType.INSURANCE_CARD.value:
        await _write_insurance(db, ctx, fields)
    elif doc_type == DocumentType.IRP_CAB_CARD.value:
        await _write_irp(db, ctx, fields)
    elif doc_type == DocumentType.TITLE.value:
        await _write_title(db, ctx, fields)
    elif doc_type == DocumentType.IFTA_FILING.value:
        await _write_ifta(db, ctx, fields)
    elif doc_type == DocumentType.FORM_2290.value:
        await _write_form_2290(db, ctx, fields)

    if corrections:
        for c in corrections:
            db.add(
                ExtractionCorrection(
                    document_id=uuid.UUID(ctx.document_id),
                    field_name=c.field,
                    original_value=c.original,
                    corrected_value=c.proposed if c.accepted else c.original,
                    correction_source="agentic_layer6",
                    tenant_id=ctx.tenant_id,
                )
            )

    result = await db.execute(select(Document).where(Document.id == uuid.UUID(ctx.document_id)))
    doc = result.scalar_one()
    doc.document_type = doc_type
    doc.document_number = fields.get("document_number") or fields.get("invoice_number")
    doc.document_date = fields.get("document_date") or fields.get("invoice_date") or fields.get("issue_date")
    doc.raw_extracted_text = ctx.l1.full_text if ctx.l1 else None
    doc.page_count = ctx.l1.page_count if ctx.l1 else None
    doc.source_format = ctx.l1.source_format if ctx.l1 else doc.source_format
    doc.parse_method = (
        "gemini_vision"
        if ctx.extraction and ctx.extraction.extraction_method == "gemini_vision"
        else (ctx.l1.parse_method if ctx.l1 else doc.parse_method)
    )
    doc.parse_confidence = ctx.validation.overall_confidence if ctx.validation else None
    doc.entity_resolution_confidence = Decimal(str(ctx.entity_resolution_confidence))
    doc.review_notes = _review_notes(ctx)
    if ctx.truck_id:
        doc.truck_id = uuid.UUID(ctx.truck_id)
    if ctx.driver_id:
        doc.driver_id = uuid.UUID(ctx.driver_id)
    if ctx.vendor_id:
        doc.vendor_id = uuid.UUID(ctx.vendor_id)

    needs_review = _needs_review(ctx, doc_type)
    doc.processing_status = (
        ProcessingStatus.NEEDS_REVIEW.value if needs_review else ProcessingStatus.COMPLETE.value
    )

    await db.commit()

    try:
        await store_chunks(
            db,
            uuid.UUID(ctx.document_id),
            ctx.l1.full_text if ctx.l1 else "",
            truck_id=uuid.UUID(ctx.truck_id) if ctx.truck_id else None,
            driver_id=uuid.UUID(ctx.driver_id) if ctx.driver_id else None,
            document_type=doc_type,
            document_date=doc.document_date,
            tenant_id=ctx.tenant_id,
        )
        await db.commit()
        ctx.affected_tables.append("document_chunks")
    except Exception:
        logger.exception("Chunk storage failed for %s", ctx.document_id)
