"""Worker document processor entrypoint."""

from __future__ import annotations

import logging

from app.extraction.pipeline import run

logger = logging.getLogger(__name__)


async def process_document(document_id: str, file_path: str, tenant_id: int = 1) -> None:
    await run(document_id, file_path, tenant_id=tenant_id)
