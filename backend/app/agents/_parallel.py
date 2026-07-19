"""Parallel execution with one AsyncSession per coroutine."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory

T = TypeVar("T")


async def run_with_session(
    fn: Callable[[AsyncSession], Awaitable[T]],
) -> T:
    async with async_session_factory() as session:
        return await fn(session)


async def gather_limited(*coros: Awaitable[T]) -> list[T]:
    return list(await asyncio.gather(*coros))


async def gather_with_sessions(
    fns: list[Callable[[AsyncSession], Awaitable[T]]],
) -> list[T]:
    return await gather_limited(*(run_with_session(fn) for fn in fns))
