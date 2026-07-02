"""Driver profile sub-agent."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.models.driver import Driver
from app.models.truck import Truck
from app.neo4j_client import get_neo4j_driver
from app.schemas.drivers import (
    CurrentDriverAssignmentInfo,
    DriverAssignmentHistoryItem,
    DriverIdentity,
    DriverLicense,
    DriverProfileResponse,
)


def _expiry_status(days: int) -> str:
    if days < 0:
        return "red"
    if days < 90:
        return "yellow"
    return "green"


async def get_driver_profile(
    db: AsyncSession,
    driver_id: uuid.UUID,
    tenant_id: int = 1,
) -> DriverProfileResponse:
    driver = (
        await db.execute(select(Driver).where(Driver.id == driver_id, Driver.tenant_id == tenant_id))
    ).scalar_one()

    today = date.today()
    days_remaining = (driver.license_expiry_date - today).days

    current_assignment: CurrentDriverAssignmentInfo | None = None
    assign_row = (
        await db.execute(
            select(Assignment, Truck)
            .join(Truck, Truck.id == Assignment.truck_id)
            .where(
                Assignment.driver_id == driver_id,
                Assignment.end_date.is_(None),
                Assignment.tenant_id == tenant_id,
            )
            .order_by(Assignment.start_date.desc())
            .limit(1)
        )
    ).first()
    if assign_row:
        assignment, truck = assign_row
        current_assignment = CurrentDriverAssignmentInfo(
            truck_unit=truck.unit_number,
            truck_make_model_year=f"{truck.year} {truck.make} {truck.model}",
            assigned_since=assignment.start_date,
            days_assigned=(today - assignment.start_date).days,
        )

    history_rows = (
        await db.execute(
            select(Assignment, Truck)
            .join(Truck, Truck.id == Assignment.truck_id)
            .where(Assignment.driver_id == driver_id, Assignment.tenant_id == tenant_id)
            .order_by(Assignment.start_date.desc())
        )
    ).all()

    history: list[DriverAssignmentHistoryItem] = []
    trucks_operated: set[int] = set()
    earliest = today
    for assignment, truck in history_rows:
        trucks_operated.add(truck.unit_number)
        if assignment.start_date < earliest:
            earliest = assignment.start_date
        duration = (assignment.end_date or today) - assignment.start_date
        history.append(
            DriverAssignmentHistoryItem(
                truck_unit=truck.unit_number,
                truck_make_model=f"{truck.make} {truck.model}",
                start_date=assignment.start_date,
                end_date=assignment.end_date,
                duration_days=duration.days,
            )
        )

    graph: dict = {"nodes": [], "edges": []}
    try:
        neo = get_neo4j_driver()
        async with neo.session() as session:
            result = await session.run(
                """
                MATCH (dr:Driver {pg_id: $driver_id})-[:ASSIGNED_TO]->(t:Truck)
                OPTIONAL MATCH (t)-[:MAINTAINED_AT]->(v:Vendor)
                RETURN dr, t, collect(v) AS vendors
                """,
                driver_id=str(driver_id),
            )
            async for rec in result:
                graph["nodes"].append({"id": str(rec["dr"]["pg_id"]), "type": "Driver"})
                if rec["t"]:
                    graph["nodes"].append({"id": str(rec["t"]["pg_id"]), "type": "Truck"})
                for v in rec["vendors"] or []:
                    if v:
                        graph["nodes"].append({"id": str(v["pg_id"]), "type": "Vendor"})
    except Exception:
        pass

    return DriverProfileResponse(
        identity=DriverIdentity(
            full_name=driver.full_name,
            driver_code=driver.driver_code,
            date_of_birth=driver.date_of_birth,
            address=driver.address,
            sex=driver.sex,
            height=driver.height,
            weight=driver.weight_lbs,
            eye_color=driver.eye_color,
        ),
        license=DriverLicense(
            number=driver.license_number,
            state=driver.license_state,
            license_class=driver.license_class,
            endorsements=driver.license_endorsements,
            restrictions=driver.license_restrictions,
            issue_date=driver.license_issue_date,
            expiry_date=driver.license_expiry_date,
            expiry_status=_expiry_status(days_remaining),
            days_remaining=days_remaining,
        ),
        current_assignment=current_assignment,
        assignment_history=history,
        total_trucks_operated=len(trucks_operated),
        time_in_fleet_days=(today - earliest).days if history else 0,
        relationships_graph=graph,
    )
