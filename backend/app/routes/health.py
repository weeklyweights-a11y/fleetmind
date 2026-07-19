import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session_factory
from app.neo4j_client import verify_connectivity
from app.redis_client import ping_redis
from app.schemas import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    postgres_status = "error"
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        postgres_status = "connected"
    except Exception:
        logger.exception("Postgres health check failed")

    redis_status = "connected" if await ping_redis() else "error"
    neo4j_status = "connected" if await verify_connectivity() else "error"

    return HealthResponse(
        postgres=postgres_status,
        redis=redis_status,
        neo4j=neo4j_status,
        status="ok",
    )
