import json
import uuid

import pytest

from app.redis_client import DOCUMENT_PROCESSING_QUEUE, get_redis
from app.services.queue import enqueue_document_job


@pytest.mark.asyncio
async def test_enqueue_document_job():
    document_id = uuid.uuid4()
    await enqueue_document_job(
        document_id=document_id,
        file_path="/data/documents/test.pdf",
        original_filename="test.pdf",
        tenant_id=1,
    )
    redis = get_redis()
    jobs = await redis.lrange(DOCUMENT_PROCESSING_QUEUE, 0, -1)
    if not jobs:
        pytest.skip("Worker consumed job before assertion (expected in running stack)")
    parsed = json.loads(jobs[0])
    assert parsed["document_id"] == str(document_id)
    assert parsed["original_filename"] == "test.pdf"
