"""Conversation API routes."""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory_search import get_memory_search
from app.chat.conversation_summary import generate_conversation_summary
from app.chat.session import end_conversation, get_active_unresolved_items, get_conversation, get_messages
from app.database import get_db
from app.schemas.conversations import (
    ConversationDetail,
    ConversationMessageOut,
    MemorySearchResponse,
    UnresolvedItemsResponse,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/search", response_model=MemorySearchResponse)
async def memory_search(
    q: str = Query("", alias="q"),
    operator: str | None = Query(None, alias="operator"),
    since_days: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> MemorySearchResponse:
    return await get_memory_search(db, q, operator, since_days=since_days)


@router.get("/operator/{operator_name}/unresolved", response_model=UnresolvedItemsResponse)
async def operator_unresolved(
    operator_name: str,
    db: AsyncSession = Depends(get_db),
) -> UnresolvedItemsResponse:
    items = await get_active_unresolved_items(db, operator_name)
    return UnresolvedItemsResponse(items=items)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_detail(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    row = await get_conversation(db, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetail.model_validate(row)


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ConversationMessageOut]:
    row = await get_conversation(db, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await get_messages(db, conversation_id)
    return [ConversationMessageOut.model_validate(m) for m in messages]


@router.post("/{conversation_id}/end")
async def end_conversation_route(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await end_conversation(db, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.commit()
    asyncio.create_task(generate_conversation_summary(conversation_id))
    return {"status": "ended", "conversation_id": str(conversation_id)}
