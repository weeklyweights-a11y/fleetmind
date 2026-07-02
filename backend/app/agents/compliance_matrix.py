"""Compliance matrix sub-agent."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._compliance import MATRIX_DEADLINE_DAYS, build_compliance_matrix, build_deadlines_from_matrix
from app.schemas.compliance import ComplianceMatrixResponse


async def get_compliance_matrix(
    db: AsyncSession,
    tenant_id: int = 1,
) -> ComplianceMatrixResponse:
    matrix, summary, score = await build_compliance_matrix(db, tenant_id)
    deadlines = build_deadlines_from_matrix(matrix, window_days=MATRIX_DEADLINE_DAYS)
    return ComplianceMatrixResponse(
        matrix=matrix,
        deadlines=deadlines,
        fleet_compliance_score=score,
        summary=summary,
    )
