import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("SKIP_EMBEDDINGS", "true")

from app.database import engine
from app.main import app


@pytest.fixture(autouse=True)
async def reset_redis_client():
    import app.redis_client as redis_client

    await redis_client.close_redis()
    yield
    await redis_client.close_redis()


@pytest.fixture(autouse=True)
async def dispose_db_engine():
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
