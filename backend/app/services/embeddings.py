"""Document chunking and embeddings."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if settings.skip_embeddings:
        return None
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def chunk_text(text: str) -> list[str]:
    if not text:
        return []
    size = settings.chunk_size_chars
    overlap = settings.chunk_overlap_chars
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    if model is None:
        return [[0.0] * 768 for _ in texts]
    return model.encode(texts, normalize_embeddings=True).tolist()


async def store_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    text: str,
    truck_id: uuid.UUID | None = None,
    driver_id: uuid.UUID | None = None,
    document_type: str | None = None,
    document_date: date | None = None,
    tenant_id: int = 1,
) -> None:
    chunks = chunk_text(text)
    if not chunks:
        return
    vectors = embed_texts(chunks)
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
        db.add(
            DocumentChunk(
                document_id=document_id,
                chunk_index=idx,
                chunk_text=chunk,
                embedding=vector,
                truck_id=truck_id,
                driver_id=driver_id,
                document_type=document_type,
                document_date=document_date,
                tenant_id=tenant_id,
            )
        )
