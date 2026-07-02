import json
import logging
import uuid

from app.redis_client import DOCUMENT_PROCESSING_QUEUE, get_redis

logger = logging.getLogger(__name__)


async def enqueue_document_job(
    document_id: uuid.UUID,
    file_path: str,
    original_filename: str,
    tenant_id: int = 1,
    retry_count: int = 0,
) -> None:
    job = {
        "document_id": str(document_id),
        "file_path": file_path,
        "original_filename": original_filename,
        "tenant_id": tenant_id,
        "retry_count": retry_count,
    }
    await get_redis().lpush(DOCUMENT_PROCESSING_QUEUE, json.dumps(job))
    logger.info("Enqueued document job for %s", document_id)
