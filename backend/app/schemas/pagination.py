import math
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    total_pages: int


def paginate_params(page: int = 1, per_page: int = 20, max_per_page: int = 200) -> tuple[int, int, int]:
    page = max(page, 1)
    per_page = min(max(per_page, 1), max_per_page)
    offset = (page - 1) * per_page
    return page, per_page, offset


def build_paginated(items: list[T], total: int, page: int, per_page: int) -> PaginatedResponse[T]:
    total_pages = max(1, math.ceil(total / per_page)) if per_page else 1
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )
