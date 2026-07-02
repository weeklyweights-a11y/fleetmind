"""Compliance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.compliance_matrix import get_compliance_matrix
from app.database import get_db
from app.schemas.compliance import ComplianceMatrixResponse

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/matrix", response_model=ComplianceMatrixResponse)
async def compliance_matrix(db: AsyncSession = Depends(get_db)) -> ComplianceMatrixResponse:
    return await get_compliance_matrix(db)
