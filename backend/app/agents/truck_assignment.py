"""Truck assignment sub-agent."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.models.driver import Driver
from app.neo4j_client import get_neo4j_driver
from app.schemas.common import GraphEdge
from app.schemas.trucks import (
    CurrentDriverAssignment,
    PreviousDriverAssignment,
    TruckAssignmentResponse,
)


def _expiry_status(days: int) -> str:
    if days < 0:
        return "red"
    if days < 90:
        return "yellow"
    return "green"


async def get_truck_assignment(
    db: AsyncSession,
    truck_id: uuid.UUID,
    tenant_id: int = 1,
) -> TruckAssignmentResponse:
    truck_status = (
        await db.execute(
            select(Assignment).where(Assignment.truck_id == truck_id).limit(1)
        )
    )
    _ = truck_status  # truck exists implied by caller

    from app.models.truck import Truck

    truck_row = (
        await db.execute(select(Truck.status).where(Truck.id == truck_id))
    ).scalar_one_or_none()

    current_result = await db.execute(
        select(Assignment, Driver)
        .join(Driver, Driver.id == Assignment.driver_id)
        .where(
            Assignment.truck_id == truck_id,
            Assignment.end_date.is_(None),
            Driver.tenant_id == tenant_id,
        )
        .order_by(Assignment.start_date.desc())
        .limit(1)
    )
    current_row = current_result.first()

    current_driver: CurrentDriverAssignment | None = None
    unassigned_reason: str | None = None

    if current_row:
        assignment, driver = current_row
        today = date.today()
        days_to_expiry = (driver.license_expiry_date - today).days
        days_assigned = (today - assignment.start_date).days
        current_driver = CurrentDriverAssignment(
            driver_id=driver.id,
            full_name=driver.full_name,
            driver_code=driver.driver_code,
            license_number=driver.license_number,
            license_class=driver.license_class,
            license_expiry_date=driver.license_expiry_date,
            license_expiry_status=_expiry_status(days_to_expiry),
            endorsements=driver.license_endorsements,
            restrictions=driver.license_restrictions,
            assigned_since=assignment.start_date,
            assignment_type=assignment.assignment_type,
            days_assigned=days_assigned,
        )
    elif truck_row == "sold":
        unassigned_reason = "Truck is sold"
    else:
        unassigned_reason = "No active driver assignment"

    history_result = await db.execute(
        select(Assignment, Driver)
        .join(Driver, Driver.id == Assignment.driver_id)
        .where(
            Assignment.truck_id == truck_id,
            Assignment.end_date.is_not(None),
            Driver.tenant_id == tenant_id,
        )
        .order_by(Assignment.start_date.desc())
    )
    previous: list[PreviousDriverAssignment] = []
    for assignment, driver in history_result.all():
        duration = (assignment.end_date - assignment.start_date).days if assignment.end_date else 0
        previous.append(
            PreviousDriverAssignment(
                full_name=driver.full_name,
                driver_code=driver.driver_code,
                start_date=assignment.start_date,
                end_date=assignment.end_date,
                duration_days=duration,
                assignment_type=assignment.assignment_type,
            )
        )

    all_drivers = len(previous) + (1 if current_driver else 0)
    if all_drivers <= 1:
        stability = "stable"
    elif all_drivers <= 3:
        stability = "moderate"
    else:
        stability = "unstable"

    chain: list[GraphEdge] = []
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (dr:Driver)-[r:ASSIGNED_TO]->(t:Truck {pg_id: $truck_id})
                RETURN dr.pg_id AS src, t.pg_id AS tgt, r.start_date AS start_date
                """,
                truck_id=str(truck_id),
            )
            async for record in result:
                chain.append(
                    GraphEdge(
                        source=str(record["src"]),
                        target=str(record["tgt"]),
                        type="ASSIGNED_TO",
                        properties={"start_date": record.get("start_date")},
                    )
                )
    except Exception:
        pass

    return TruckAssignmentResponse(
        current_driver=current_driver,
        unassigned_reason=unassigned_reason,
        previous_drivers=previous,
        total_drivers_historically=all_drivers,
        assignment_stability=stability,
        assignment_chain=chain,
    )
