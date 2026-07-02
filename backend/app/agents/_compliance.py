"""Shared compliance evaluation logic."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.models.driver import Driver
from app.models.emission_cert import EmissionCert
from app.models.insurance_coverage import InsuranceCoverage
from app.models.maintenance_event import MaintenanceEvent
from app.models.registration import Registration
from app.models.title import Title
from app.models.truck import Truck
from app.schemas.common import ComplianceCategoryDetail, ComplianceCell, ComplianceStatusColor
from app.schemas.compliance import ComplianceDeadline, ComplianceMatrixRow, ComplianceMatrixSummary
from app.schemas.trucks import ComplianceCategories, UrgentComplianceItem

URGENT_DEADLINE_DAYS = 7
MATRIX_DEADLINE_DAYS = 90


def _days_until(target: date | None, today: date | None = None) -> int | None:
    if target is None:
        return None
    today = today or date.today()
    return (target - today).days


def _expiry_status(days: int | None, green_min: int, yellow_min: int = 1) -> ComplianceStatusColor:
    if days is None:
        return "grey"
    if days < 0:
        return "red"
    if days < yellow_min:
        return "red"
    if days < green_min:
        return "yellow"
    return "green"


def rollup_compliance_status(statuses: list[ComplianceStatusColor]) -> str:
    if not statuses or all(s == "grey" for s in statuses):
        return "incomplete"
    if any(s == "red" for s in statuses):
        return "red"
    if any(s == "yellow" for s in statuses):
        return "yellow"
    if any(s == "grey" for s in statuses):
        return "incomplete"
    return "green"


def overall_status_from_categories(statuses: list[ComplianceStatusColor]) -> str:
    if all(s == "green" for s in statuses):
        return "compliant"
    if any(s == "red" for s in statuses):
        return "non_compliant"
    if any(s == "yellow" for s in statuses):
        return "attention_needed"
    return "incomplete"


async def _current_driver_for_truck(
    db: AsyncSession, truck_id: uuid.UUID, tenant_id: int
) -> Driver | None:
    result = await db.execute(
        select(Driver)
        .join(Assignment, Assignment.driver_id == Driver.id)
        .where(
            Assignment.truck_id == truck_id,
            Assignment.end_date.is_(None),
            Driver.tenant_id == tenant_id,
        )
        .order_by(Assignment.start_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _has_emissions_maintenance(db: AsyncSession, truck_id: uuid.UUID, tenant_id: int) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(MaintenanceEvent)
        .where(
            MaintenanceEvent.truck_id == truck_id,
            MaintenanceEvent.tenant_id == tenant_id,
            MaintenanceEvent.category == "Emissions",
        )
    )
    return (result.scalar_one() or 0) > 0


async def build_truck_compliance_categories(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
    today: date | None = None,
) -> ComplianceCategories:
    today = today or date.today()

    ins = (
        await db.execute(
            select(InsuranceCoverage)
            .where(InsuranceCoverage.truck_id == truck_id, InsuranceCoverage.tenant_id == tenant_id)
            .order_by(InsuranceCoverage.expiry_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    reg = (
        await db.execute(
            select(Registration)
            .where(Registration.truck_id == truck_id, Registration.tenant_id == tenant_id)
            .order_by(Registration.expiry_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    title = (
        await db.execute(
            select(Title)
            .where(Title.truck_id == truck_id, Title.tenant_id == tenant_id)
            .order_by(Title.issue_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    emission = (
        await db.execute(
            select(EmissionCert)
            .where(EmissionCert.truck_id == truck_id, EmissionCert.tenant_id == tenant_id)
            .order_by(EmissionCert.test_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    driver = await _current_driver_for_truck(db, truck_id, tenant_id)

    if ins:
        ins_days = _days_until(ins.expiry_date, today)
        ins_status = _expiry_status(ins_days, green_min=30)
        insurance = ComplianceCategoryDetail(
            status=ins_status,
            policy_number=ins.policy_number,
            insurer=ins.insurer_name,
            effective_date=str(ins.effective_date),
            expiry_date=str(ins.expiry_date),
            days_remaining=ins_days,
            source_document_id=str(ins.source_document_id),
        )
    else:
        insurance = ComplianceCategoryDetail(status="grey")

    if reg:
        reg_days = _days_until(reg.expiry_date, today)
        reg_status = _expiry_status(reg_days, green_min=30)
        registration = ComplianceCategoryDetail(
            status=reg_status,
            plate_number=reg.plate_number,
            registration_number=reg.registration_number,
            expiry_date=str(reg.expiry_date),
            days_remaining=reg_days,
            source_document_id=str(reg.source_document_id),
        )
    else:
        registration = ComplianceCategoryDetail(status="grey")

    if title:
        title_status: ComplianceStatusColor = "yellow" if title.lien_holder else "green"
        title_detail = ComplianceCategoryDetail(
            status=title_status,
            title_number=title.title_number,
            issue_date=str(title.issue_date),
            lien_holder=title.lien_holder,
            source_document_id=str(title.source_document_id),
        )
    else:
        title_detail = ComplianceCategoryDetail(status="grey")

    if emission:
        em_days = _days_until(emission.next_due_date, today) if emission.next_due_date else None
        em_status = _expiry_status(em_days, green_min=30) if em_days is not None else "green"
        emission_detail = ComplianceCategoryDetail(
            status=em_status,
            last_test_date=str(emission.test_date),
            result=emission.result,
            next_due_date=str(emission.next_due_date) if emission.next_due_date else None,
            days_remaining=em_days,
            source_document_id=str(emission.source_document_id) if emission.source_document_id else None,
        )
    elif await _has_emissions_maintenance(db, truck_id, tenant_id):
        emission_detail = ComplianceCategoryDetail(
            status="yellow",
            note="Emissions-related maintenance on record; no emission certificate",
        )
    else:
        emission_detail = ComplianceCategoryDetail(status="grey")

    if driver:
        cdl_days = _days_until(driver.license_expiry_date, today)
        cdl_status = _expiry_status(cdl_days, green_min=90)
        driver_cdl = ComplianceCategoryDetail(
            status=cdl_status,
            driver_name=driver.full_name,
            license_number=driver.license_number,
            expiry_date=str(driver.license_expiry_date),
            days_remaining=cdl_days,
        )
    else:
        driver_cdl = ComplianceCategoryDetail(status="grey")

    if driver and driver.medical_cert_expiry_date:
        med_days = _days_until(driver.medical_cert_expiry_date, today)
        med_status = _expiry_status(med_days, green_min=90)
        medical_cert = ComplianceCategoryDetail(
            status=med_status,
            expiry_date=str(driver.medical_cert_expiry_date),
            days_remaining=med_days,
        )
    else:
        medical_cert = ComplianceCategoryDetail(status="grey" if driver else "grey")

    return ComplianceCategories(
        insurance=insurance,
        registration=registration,
        title=title_detail,
        emission=emission_detail,
        driver_cdl=driver_cdl,
        medical_cert=medical_cert,
    )


def categories_to_cells(categories: ComplianceCategories) -> dict[str, ComplianceCell]:
    return {
        "insurance": ComplianceCell(
            status=categories.insurance.status,
            days=categories.insurance.days_remaining,
            expiry=categories.insurance.expiry_date,
        ),
        "registration": ComplianceCell(
            status=categories.registration.status,
            days=categories.registration.days_remaining,
            expiry=categories.registration.expiry_date,
        ),
        "title": ComplianceCell(status=categories.title.status),
        "emission": ComplianceCell(
            status=categories.emission.status,
            days=categories.emission.days_remaining,
            expiry=categories.emission.next_due_date,
        ),
        "driver_cdl": ComplianceCell(
            status=categories.driver_cdl.status,
            days=categories.driver_cdl.days_remaining,
            expiry=categories.driver_cdl.expiry_date,
            driver_name=categories.driver_cdl.driver_name,
        ),
        "medical_cert": ComplianceCell(
            status=categories.medical_cert.status,
            days=categories.medical_cert.days_remaining,
            expiry=categories.medical_cert.expiry_date,
        ),
    }


def build_urgent_items(categories: ComplianceCategories, window_days: int = URGENT_DEADLINE_DAYS) -> list[UrgentComplianceItem]:
    items: list[UrgentComplianceItem] = []
    mapping = [
        ("insurance", categories.insurance),
        ("registration", categories.registration),
        ("emission", categories.emission),
        ("driver_cdl", categories.driver_cdl),
        ("medical_cert", categories.medical_cert),
    ]
    for name, cat in mapping:
        if cat.status in ("yellow", "red") and cat.days_remaining is not None and cat.days_remaining <= window_days:
            items.append(
                UrgentComplianceItem(
                    category=name,
                    status=cat.status,
                    days_remaining=cat.days_remaining,
                    expiry_date=cat.expiry_date or cat.next_due_date,
                    description=cat.note,
                )
            )
    items.sort(key=lambda x: x.days_remaining if x.days_remaining is not None else 9999)
    return items


def build_deadlines_from_matrix(
    matrix: list[ComplianceMatrixRow],
    window_days: int = MATRIX_DEADLINE_DAYS,
) -> list[ComplianceDeadline]:
    deadlines: list[ComplianceDeadline] = []
    today = date.today()
    for row in matrix:
        for ctype, cell in [
            ("insurance", row.insurance),
            ("registration", row.registration),
            ("emission", row.emission),
            ("driver_cdl", row.driver_cdl),
            ("medical_cert", row.medical_cert),
        ]:
            if cell.expiry and cell.status in ("yellow", "red", "green"):
                try:
                    exp = date.fromisoformat(cell.expiry)
                except ValueError:
                    continue
                days = (exp - today).days
                if days <= window_days:
                    deadlines.append(
                        ComplianceDeadline(
                            truck_unit=row.truck_unit,
                            compliance_type=ctype,
                            expiry_date=cell.expiry,
                            days_remaining=days,
                            severity=cell.status if cell.status != "green" else "yellow",
                        )
                    )
    deadlines.sort(key=lambda d: d.days_remaining)
    return deadlines


async def build_compliance_matrix(
    db: AsyncSession,
    tenant_id: int = 1,
) -> tuple[list[ComplianceMatrixRow], ComplianceMatrixSummary, float]:
    trucks = (
        await db.execute(
            select(Truck)
            .where(Truck.tenant_id == tenant_id, Truck.status == "active")
            .order_by(Truck.unit_number)
        )
    ).scalars().all()

    matrix: list[ComplianceMatrixRow] = []
    green = yellow = red = grey = 0

    for truck in trucks:
        categories = await build_truck_compliance_categories(db, truck.id, tenant_id)
        cells = categories_to_cells(categories)
        for cell in cells.values():
            if cell.status == "green":
                green += 1
            elif cell.status == "yellow":
                yellow += 1
            elif cell.status == "red":
                red += 1
            else:
                grey += 1

        matrix.append(
            ComplianceMatrixRow(
                truck_unit=truck.unit_number,
                truck_make_model=f"{truck.year} {truck.make} {truck.model}",
                insurance=cells["insurance"],
                registration=cells["registration"],
                title=cells["title"],
                emission=cells["emission"],
                driver_cdl=cells["driver_cdl"],
                medical_cert=cells["medical_cert"],
            )
        )

    total_cells = green + yellow + red + grey
    score = round(100 * green / total_cells, 1) if total_cells else 0.0
    summary = ComplianceMatrixSummary(
        green_count=green,
        yellow_count=yellow,
        red_count=red,
        grey_count=grey,
    )
    return matrix, summary, score


async def compliance_snapshot_counts(
    db: AsyncSession,
    tenant_id: int = 1,
) -> tuple[int, int, int, int, list[dict[str, Any]]]:
    matrix, _, _ = await build_compliance_matrix(db, tenant_id)
    fully = warnings = expirations = incomplete = 0
    all_urgent: list[dict[str, Any]] = []

    for row in matrix:
        statuses = [
            row.insurance.status,
            row.registration.status,
            row.title.status,
            row.emission.status,
            row.driver_cdl.status,
            row.medical_cert.status,
        ]
        rollup = rollup_compliance_status(statuses)
        if rollup == "green":
            fully += 1
        elif rollup == "yellow":
            warnings += 1
        elif rollup == "red":
            expirations += 1
        else:
            incomplete += 1

    for row in matrix:
        for ctype, cell in [
            ("insurance", row.insurance),
            ("registration", row.registration),
            ("driver_cdl", row.driver_cdl),
        ]:
            if cell.status in ("yellow", "red") and cell.days is not None and cell.days <= URGENT_DEADLINE_DAYS:
                all_urgent.append(
                    {
                        "truck_unit": row.truck_unit,
                        "compliance_type": ctype,
                        "days_remaining": cell.days,
                        "expiry_date": cell.expiry,
                    }
                )
    all_urgent.sort(key=lambda x: x.get("days_remaining", 9999))
    return fully, warnings, expirations, incomplete, all_urgent
