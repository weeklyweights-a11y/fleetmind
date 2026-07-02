"""Conversation API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory_search import get_memory_search
from app.database import get_db
from app.schemas.conversations import MemorySearchResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/search", response_model=MemorySearchResponse)
async def memory_search(
    q: str = Query("", alias="q"),
    operator: str | None = Query(None, alias="operator"),
    db: AsyncSession = Depends(get_db),
) -> MemorySearchResponse:
    return await get_memory_search(db, q, operator)
