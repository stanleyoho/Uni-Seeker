from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import v1_router
from app.config import settings
from app.logging_config import setup_logging
from app.middleware.error_handler import register_error_handlers
from app.modules.sync_manager.auto_scheduler import AutoSyncScheduler
from app.services.job_worker import BacktestJobWorker

auto_scheduler = AutoSyncScheduler()
job_worker = BacktestJobWorker()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    auto_scheduler.start()
    await job_worker.start()
    yield
    await job_worker.stop()
    auto_scheduler.stop()

    from app.cache import close_redis

    await close_redis()


def create_app() -> FastAPI:
    setup_logging(settings.debug)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
        expose_headers=["X-Request-Id"],
    )

    app.include_router(v1_router)

    @app.get("/health")
    async def health() -> dict:
        status: dict = {"status": "ok", "services": {}}

        # Check DB
        try:
            from app.database import async_session

            async with async_session() as session:
                await session.execute(text("SELECT 1"))
            status["services"]["database"] = "ok"
        except Exception:
            status["services"]["database"] = "error"
            status["status"] = "degraded"

        # Check Redis
        try:
            from app.cache import get_redis

            r = await get_redis()
            await r.ping()
            status["services"]["redis"] = "ok"
        except Exception:
            status["services"]["redis"] = "error"
            status["status"] = "degraded"

        return status

    return app


app = create_app()
