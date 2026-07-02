"""Neo4j graph writes."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.config import settings
from app.neo4j_client import get_neo4j_driver

logger = logging.getLogger(__name__)


async def _run(cypher: str, params: dict[str, Any]) -> None:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run(cypher, params)


async def write_with_retry(write_fn, *args, **kwargs) -> None:
    last_exc: Exception | None = None
    for attempt in range(settings.neo4j_write_max_retries):
        try:
            await write_fn(*args, **kwargs)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("Neo4j write attempt %s failed: %s", attempt + 1, exc)
            await asyncio.sleep(0.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


async def merge_truck(truck_id: uuid.UUID, fields: dict, tenant_id: int = 1) -> None:
    await _run(
        """
        MERGE (t:Truck {pg_id: $pg_id})
        SET t.vin = $vin, t.unit_number = $unit_number, t.make = $make,
            t.model = $model, t.year = $year, t.color = $color,
            t.status = $status, t.tenant_id = $tenant_id
        """,
        {
            "pg_id": str(truck_id),
            "vin": fields.get("vin"),
            "unit_number": fields.get("unit_number") or fields.get("fleet_unit_no"),
            "make": fields.get("make"),
            "model": fields.get("model"),
            "year": fields.get("year"),
            "color": fields.get("color"),
            "status": fields.get("status", "active"),
            "tenant_id": tenant_id,
        },
    )


async def merge_driver(driver_id: uuid.UUID, fields: dict, tenant_id: int = 1) -> None:
    await _run(
        """
        MERGE (d:Driver {pg_id: $pg_id})
        SET d.full_name = $full_name, d.license_number = $license_number,
            d.driver_code = $driver_code, d.tenant_id = $tenant_id
        """,
        {
            "pg_id": str(driver_id),
            "full_name": fields.get("full_name"),
            "license_number": fields.get("license_number"),
            "driver_code": fields.get("driver_code"),
            "tenant_id": tenant_id,
        },
    )


async def merge_vendor_node(vendor_id: uuid.UUID, tenant_id: int = 1, name: str | None = None) -> None:
    await _run(
        """
        MERGE (v:Vendor {pg_id: $pg_id})
        SET v.tenant_id = $tenant_id, v.name = coalesce($name, v.name)
        """,
        {"pg_id": str(vendor_id), "tenant_id": tenant_id, "name": name},
    )


async def merge_document(
    document_id: uuid.UUID,
    document_type: str,
    document_number: str | None,
    document_date: Any,
    tenant_id: int = 1,
) -> None:
    await _run(
        """
        MERGE (d:Document {pg_id: $pg_id})
        SET d.document_type = $document_type, d.document_number = $document_number,
            d.document_date = $document_date, d.tenant_id = $tenant_id
        """,
        {
            "pg_id": str(document_id),
            "document_type": document_type,
            "document_number": document_number,
            "document_date": str(document_date) if document_date else None,
            "tenant_id": tenant_id,
        },
    )


async def link_has_document(truck_id: uuid.UUID, document_id: uuid.UUID) -> None:
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id}), (d:Document {pg_id: $document_id})
        MERGE (t)-[:HAS_DOCUMENT]->(d)
        """,
        {"truck_id": str(truck_id), "document_id": str(document_id)},
    )


async def link_driver_document(driver_id: uuid.UUID, document_id: uuid.UUID) -> None:
    await _run(
        """
        MATCH (dr:Driver {pg_id: $driver_id}), (d:Document {pg_id: $document_id})
        MERGE (dr)-[:HAS_DOCUMENT]->(d)
        """,
        {"driver_id": str(driver_id), "document_id": str(document_id)},
    )


async def write_purchase(
    truck_id: uuid.UUID, vendor_id: uuid.UUID, document_id: uuid.UUID, fields: dict, tenant_id: int = 1
) -> None:
    await merge_truck(truck_id, {**fields, "status": "active"}, tenant_id)
    await merge_vendor_node(vendor_id, tenant_id)
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id}), (v:Vendor {pg_id: $vendor_id})
        MERGE (t)-[r:PURCHASED_FROM]->(v)
        SET r.date = $date, r.price = $price, r.odometer = $odometer
        """,
        {
            "vendor_id": str(vendor_id),
            "truck_id": str(truck_id),
            "date": str(fields.get("document_date") or fields.get("acquired_date")),
            "price": float(fields.get("purchase_price") or 0),
            "odometer": fields.get("odometer") or fields.get("initial_odometer"),
        },
    )
    await merge_document(
        document_id, "bill_of_sale_purchase", fields.get("document_number"), fields.get("document_date"), tenant_id
    )
    await link_has_document(truck_id, document_id)


async def write_sale(
    truck_id: uuid.UUID,
    vendor_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
) -> None:
    await merge_truck(truck_id, {**fields, "status": "sold"}, tenant_id)
    await merge_vendor_node(vendor_id, tenant_id)
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id}), (v:Vendor {pg_id: $vendor_id})
        MERGE (t)-[r:SOLD_TO]->(v)
        SET r.date = $date, r.price = $price
        """,
        {
            "truck_id": str(truck_id),
            "vendor_id": str(vendor_id),
            "date": str(fields.get("document_date")),
            "price": float(fields.get("purchase_price") or fields.get("sale_price") or 0),
        },
    )
    await merge_document(
        document_id, "bill_of_sale_sale", fields.get("document_number"), fields.get("document_date"), tenant_id
    )
    await link_has_document(truck_id, document_id)


async def write_cdl(
    driver_id: uuid.UUID,
    truck_id: uuid.UUID | None,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
) -> None:
    await merge_driver(driver_id, fields, tenant_id)
    await merge_document(document_id, "cdl", fields.get("driver_code"), fields.get("license_issue_date"), tenant_id)
    await link_driver_document(driver_id, document_id)
    if truck_id:
        await merge_truck(truck_id, fields, tenant_id)
        await _run(
            """
            MATCH (dr:Driver {pg_id: $driver_id}), (t:Truck {pg_id: $truck_id})
            MERGE (dr)-[r:ASSIGNED_TO]->(t)
            SET r.start_date = $start_date, r.end_date = null, r.assignment_type = 'primary'
            """,
            {
                "driver_id": str(driver_id),
                "truck_id": str(truck_id),
                "start_date": str(fields.get("license_issue_date")),
            },
        )
        await link_has_document(truck_id, document_id)


async def write_maintenance(
    truck_id: uuid.UUID,
    vendor_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
) -> None:
    await merge_vendor_node(vendor_id, tenant_id)
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id}), (v:Vendor {pg_id: $vendor_id})
        CREATE (t)-[:MAINTAINED_AT {
            service_date: $service_date, category: $category,
            total_cost: $total_cost, invoice_number: $invoice_number
        }]->(v)
        """,
        {
            "vendor_id": str(vendor_id),
            "truck_id": str(truck_id),
            "service_date": str(fields.get("invoice_date")),
            "category": fields.get("category"),
            "total_cost": float(fields.get("total") or 0),
            "invoice_number": fields.get("invoice_number"),
        },
    )
    await merge_document(
        document_id, "service_invoice", fields.get("invoice_number"), fields.get("invoice_date"), tenant_id
    )
    await link_has_document(truck_id, document_id)


async def write_insurance(
    truck_id: uuid.UUID,
    coverage_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
    insurer_vendor_id: uuid.UUID | None = None,
) -> None:
    await merge_truck(truck_id, fields, tenant_id)
    if insurer_vendor_id:
        await merge_vendor_node(insurer_vendor_id, tenant_id, fields.get("insurer_name"))
    await _run(
        """
        MERGE (p:InsurancePolicy {pg_id: $pg_id})
        SET p.policy_number = $policy_number, p.insurer_name = $insurer_name,
            p.effective_date = $effective_date, p.expiry_date = $expiry_date,
            p.liability_limit = $liability_limit, p.tenant_id = $tenant_id
        WITH p
        MATCH (t:Truck {pg_id: $truck_id})
        MERGE (t)-[r:COVERED_BY]->(p)
        SET r.effective_date = $effective_date, r.expiry_date = $expiry_date,
            r.coverage_type = $coverage_type
        """,
        {
            "pg_id": str(coverage_id),
            "truck_id": str(truck_id),
            "policy_number": fields.get("policy_number"),
            "insurer_name": fields.get("insurer_name"),
            "effective_date": str(fields.get("effective_date")),
            "expiry_date": str(fields.get("expiry_date")),
            "liability_limit": str(fields.get("liability_limit") or ""),
            "coverage_type": fields.get("coverage_type", "Liability"),
            "tenant_id": tenant_id,
        },
    )
    if insurer_vendor_id:
        await _run(
            """
            MATCH (p:InsurancePolicy {pg_id: $pg_id}), (v:Vendor {pg_id: $vendor_id})
            MERGE (p)-[:ISSUED_BY]->(v)
            """,
            {"pg_id": str(coverage_id), "vendor_id": str(insurer_vendor_id)},
        )
    await merge_document(
        document_id, "insurance_card", fields.get("policy_number"), fields.get("effective_date"), tenant_id
    )
    await link_has_document(truck_id, document_id)


async def write_registration(
    truck_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
) -> None:
    await merge_truck(truck_id, fields, tenant_id)
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id})
        MERGE (j:Jurisdiction {name: 'Kansas'})
        CREATE (t)-[r:REGISTERED_IN]->(j)
        SET r.effective_date = $effective_date, r.expiry_date = $expiry_date,
            r.plate_number = $plate_number, r.state = 'Kansas'
        """,
        {
            "truck_id": str(truck_id),
            "effective_date": str(fields.get("effective_date")),
            "expiry_date": str(fields.get("expiry_date")),
            "plate_number": fields.get("plate_number"),
        },
    )
    await merge_document(
        document_id, "irp_cab_card", fields.get("plate_number"), fields.get("effective_date"), tenant_id
    )
    await link_has_document(truck_id, document_id)


async def write_title(
    truck_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    tenant_id: int = 1,
) -> None:
    await merge_truck(truck_id, fields, tenant_id)
    await _run(
        """
        MATCH (t:Truck {pg_id: $truck_id})
        MERGE (j:Jurisdiction {name: 'Kansas'})
        CREATE (t)-[r:TITLED_IN]->(j)
        SET r.title_number = $title_number, r.issue_date = $issue_date, r.state = 'Kansas'
        """,
        {
            "truck_id": str(truck_id),
            "title_number": fields.get("title_number"),
            "issue_date": str(fields.get("issue_date")),
        },
    )
    await merge_document(document_id, "title", fields.get("title_number"), fields.get("issue_date"), tenant_id)
    await link_has_document(truck_id, document_id)


async def write_ifta(
    filing_id: uuid.UUID,
    document_id: uuid.UUID,
    fields: dict,
    vehicle_details: list[dict],
    tenant_id: int = 1,
) -> None:
    await _run(
        """
        MERGE (f:IFTAFiling {pg_id: $pg_id})
        SET f.quarter = $quarter, f.filing_date = $filing_date,
            f.total_miles = $total_miles, f.total_gallons = $total_gallons,
            f.average_mpg = $average_mpg, f.tenant_id = $tenant_id
        """,
        {
            "pg_id": str(filing_id),
            "quarter": fields.get("quarter"),
            "filing_date": str(fields.get("filing_date")),
            "total_miles": fields.get("total_miles"),
            "total_gallons": fields.get("total_gallons"),
            "average_mpg": float(fields.get("average_fleet_mpg") or 0),
            "tenant_id": tenant_id,
        },
    )
    for vd in vehicle_details:
        if not vd.get("truck_pg_id"):
            continue
        await _run(
            """
            MATCH (t:Truck {pg_id: $truck_id}), (f:IFTAFiling {pg_id: $filing_id})
            MERGE (t)-[r:REPORTED_IN]->(f)
            SET r.miles = $miles, r.gallons = $gallons
            """,
            {
                "truck_id": vd["truck_pg_id"],
                "filing_id": str(filing_id),
                "miles": vd.get("miles"),
                "gallons": vd.get("gallons"),
            },
        )
    await merge_document(document_id, "ifta_filing", fields.get("quarter"), fields.get("filing_date"), tenant_id)


async def repair_document_graph(document_id: uuid.UUID) -> None:
    logger.info("Graph repair stub for document %s — re-run pipeline for document", document_id)
