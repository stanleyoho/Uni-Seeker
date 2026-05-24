"""Plan 8 T2 — FastAPI middleware that propagates trace_id.

Inbound: takes ``X-Request-Id`` header if present, otherwise generates
a fresh trace via ``new_trace_id()``. Binds it through ``trace_context``
so structlog automatically merges it into every log line of the request.
Outbound: echoes the trace_id back as ``X-Request-Id``.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.obs.trace import new_trace_id, trace_context

_HEADER = "x-request-id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get(_HEADER) or new_trace_id()
        with trace_context(trace_id):
            response = await call_next(request)
        response.headers["X-Request-Id"] = trace_id
        return response
