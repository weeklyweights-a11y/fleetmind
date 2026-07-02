"""Vendor API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents._lookup import resolve_vendor_id
from app.agents.vendor_analysis import get_vendor_analysis_detail, get_vendor_analysis_fleet
from app.database import get_db
from app.schemas.vendors import VendorDetailResponse, VendorFleetResponse

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


@router.get("", response_model=VendorFleetResponse)
async def vendors_fleet(db: AsyncSession = Depends(get_db)) -> VendorFleetResponse:
    return await get_vendor_analysis_fleet(db)


@router.get("/{id}", response_model=VendorDetailResponse)
async def vendor_detail(id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> VendorDetailResponse:
    vendor_id = await resolve_vendor_id(db, str(id))
    return await get_vendor_analysis_detail(db, vendor_id)
