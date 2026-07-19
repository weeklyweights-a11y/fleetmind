import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import async_session_factory
from app.exceptions import (
    DatabaseError,
    DocumentProcessingError,
    FleetMindError,
    is_not_found_error,
)
from app.neo4j_client import apply_migrations, check_graph_integrity, close_neo4j_driver
from app.redis_client import close_redis
from app.routes.admin import router as admin_router
from app.routes.anomalies import router as anomalies_router
from app.routes.compliance import router as compliance_router
from app.routes.conversations import router as conversations_router
from app.routes.documents import router as documents_router
from app.routes.drivers import router as drivers_router
from app.routes.fleet import router as fleet_router
from app.routes.graph import router as graph_router
from app.routes.health import router as health_router
from app.routes.trucks import router as trucks_router
from app.routes.vendors import router as vendors_router
from app.routes.websocket import router as websocket_router
from app.schemas import ErrorResponse
from app.websocket.notifier import run_notify_listener

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

notify_stop_event = asyncio.Event()
notify_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global notify_task

    from pathlib import Path

    Path(settings.document_storage_path).mkdir(parents=True, exist_ok=True)

    await apply_migrations()
    async with async_session_factory() as session:
        await check_graph_integrity(session)

    notify_stop_event.clear()
    notify_task = asyncio.create_task(run_notify_listener(notify_stop_event))
    logger.info("FleetMind API started")

    yield

    notify_stop_event.set()
    if notify_task is not None:
        notify_task.cancel()
        try:
            await notify_task
        except asyncio.CancelledError:
            pass

    await close_redis()
    await close_neo4j_driver()
    logger.info("FleetMind API stopped")


app = FastAPI(title="FleetMind API", lifespan=lifespan, redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FleetMindError)
async def fleetmind_error_handler(request: Request, exc: FleetMindError):
    status_code = 500
    if is_not_found_error(exc):
        status_code = 404
    elif isinstance(exc, DocumentProcessingError):
        if exc.error_code in {"INVALID_FILE_TYPE", "FILE_TOO_LARGE"}:
            status_code = 400
        elif exc.error_code == "QUEUE_ENQUEUE_FAILED":
            status_code = 500
        else:
            status_code = 400
    elif exc.error_code == "VALIDATION_ERROR":
        status_code = 422
    elif exc.error_code == "DATABASE_ERROR":
        status_code = 500

    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": exc.errors()},
        ).model_dump(),
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error")
    db_exc = DatabaseError(str(exc))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code=db_exc.error_code,
            message=db_exc.message,
            details=db_exc.details,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An internal error occurred",
            details={"type": type(exc).__name__},
        ).model_dump(),
    )


app.include_router(health_router)
app.include_router(trucks_router)
app.include_router(drivers_router)
app.include_router(fleet_router)
app.include_router(compliance_router)
app.include_router(vendors_router)
app.include_router(anomalies_router)
app.include_router(admin_router)
app.include_router(graph_router)
app.include_router(conversations_router)
app.include_router(documents_router)
app.include_router(websocket_router)
