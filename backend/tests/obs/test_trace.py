"""Plan 8 T2 — trace_id ContextVar + FastAPI middleware tests."""
import io
import json
from contextlib import redirect_stdout

import pytest


def test_new_trace_id_returns_unique_strings():
    from app.obs.trace import new_trace_id
    ids = {new_trace_id() for _ in range(50)}
    assert len(ids) == 50
    # All should be UUID-ish (length 36 with dashes, or 32 hex)
    for i in ids:
        assert len(i) >= 32


def test_trace_context_binds_to_structlog(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    from app.obs.logging import configure_logging, get_logger
    from app.obs.trace import trace_context
    configure_logging(service="uni-seeker-backend")
    log = get_logger("test")
    buf = io.StringIO()
    with redirect_stdout(buf):
        with trace_context("test-trace-xyz"):
            log.info("inside")
        log.info("outside")
    lines = [l for l in buf.getvalue().strip().split("\n") if l.strip()]
    inside = json.loads(lines[0])
    outside = json.loads(lines[1])
    assert inside["trace_id"] == "test-trace-xyz"
    assert "trace_id" not in outside or outside["trace_id"] is None


@pytest.mark.asyncio
async def test_fastapi_middleware_propagates_x_request_id(monkeypatch):
    """Inbound X-Request-Id header is used as trace_id and echoed back."""
    monkeypatch.setenv("ENV", "test")
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.middleware.trace_id import TraceIdMiddleware
    from app.obs.trace import TRACE_ID

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/probe")
    async def probe():
        return {"trace_id": TRACE_ID.get()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/probe", headers={"X-Request-Id": "abc-123"})
    assert r.status_code == 200
    assert r.headers["X-Request-Id"] == "abc-123"
    assert r.json()["trace_id"] == "abc-123"


@pytest.mark.asyncio
async def test_fastapi_middleware_generates_when_missing(monkeypatch):
    """No incoming X-Request-Id → middleware generates one and echoes."""
    monkeypatch.setenv("ENV", "test")
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.middleware.trace_id import TraceIdMiddleware
    from app.obs.trace import TRACE_ID

    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/probe")
    async def probe():
        return {"trace_id": TRACE_ID.get()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/probe")
    assert r.status_code == 200
    generated = r.headers.get("X-Request-Id")
    assert generated and len(generated) >= 32
    assert r.json()["trace_id"] == generated
