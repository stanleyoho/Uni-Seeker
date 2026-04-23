from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import v1_router
from app.config import settings
from app.logging_config import setup_logging
from app.middleware.error_handler import register_error_handlers


def create_app() -> FastAPI:
    setup_logging(settings.debug)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/api/openapi.json",
    )

    register_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
