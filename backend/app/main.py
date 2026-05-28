import logging as _logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sqlalchemy import text

import app.obs.metrics
from app.api.v1.router import v1_router
from app.config import settings
from app.logging_config import setup_logging
from app.middleware.compliance_purifier import CompliancePurifierMiddleware
from app.middleware.error_handler import register_error_handlers
from app.middleware.trace_id import TraceIdMiddleware
from app.modules.sync_manager.auto_scheduler import AutoSyncScheduler
from app.obs.logging import configure_logging
from app.obs.sentry import init_sentry
from app.scheduler import lifespan_scheduler as f13_lifespan_scheduler
from app.services.job_worker import BacktestJobWorker

auto_scheduler = AutoSyncScheduler()
job_worker = BacktestJobWorker()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(service="uni-seeker-backend")
    init_sentry(
        service="uni-seeker-backend",
        extra_integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
            AsyncioIntegration(),
            LoggingIntegration(level=_logging.INFO, event_level=_logging.ERROR),
        ],
    )
    # Plan 8 T5: Prometheus /metrics expose is wired in create_app()
    # (BEFORE uvicorn starts the lifespan) — starlette refuses
    # add_middleware after startup. Instrument call is left as a no-op
    # safety in case future code re-enters lifespan; the .expose() side
    # effect on a started app would re-throw the same RuntimeError.
    auto_scheduler.start()
    await job_worker.start()
    # 13F refresh scheduler — UTC-anchored Pro daily / Basic weekly.
    # Kept distinct from AutoSyncScheduler (Asia/Taipei) so the two
    # cron cadences cannot interfere with each other's blast radius.
    async with f13_lifespan_scheduler():
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

    # Plan 8 T5: register Prometheus middleware BEFORE uvicorn enters
    # lifespan. starlette throws RuntimeError("Cannot add middleware
    # after an application has started") if this lives inside lifespan.
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Next.js dev fallback when port 3000 is busy
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
        expose_headers=["X-Request-Id"],
    )

    # Plan 4.5 T9: outermost middleware — sees fully serialized JSON/text bodies
    # last on the way out, so its regex sanitization wins over every endpoint.
    app.add_middleware(CompliancePurifierMiddleware)

    # Plan 8 T2: trace_id propagation — registered LAST so it sits at the
    # outermost layer (Starlette evaluates add_middleware in reverse order:
    # last added = first to see the request), ensuring every inbound request
    # gets a trace_id bound before CompliancePurifier or any downstream logs.
    app.add_middleware(TraceIdMiddleware)

    app.include_router(v1_router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        status: dict[str, Any] = {"status": "ok", "services": {}}

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
            await r.ping()  # type: ignore[misc, unused-ignore]  # cross-env: needed on older redis-py, unused on newer
            status["services"]["redis"] = "ok"
        except Exception:
            status["services"]["redis"] = "error"
            status["status"] = "degraded"

        # Check WebSocket
        from app.services.websocket_manager import ws_manager

        status["services"]["websocket"] = {
            "connections": ws_manager.connection_count,
        }

        return status

    return app


app = create_app()  # type: ignore[assignment]  # line 15 `import app.obs.metrics` binds `app` to the package; this reassigns to the FastAPI instance — intended.
