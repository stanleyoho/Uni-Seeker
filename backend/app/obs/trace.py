"""Plan 8 T2 — trace_id ContextVar + helpers.

Module-level ``TRACE_ID`` ContextVar carries the current request / job
trace identifier. Helpers bind it both to the ContextVar and to
structlog.contextvars so any subsequent log line picks it up via the
``merge_contextvars`` processor wired in T1.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

import structlog

TRACE_ID: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """Return a fresh trace identifier. Currently UUIDv4 hex with dashes."""
    return str(uuid.uuid4())


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """Bind a trace_id for the duration of the context block.

    Args:
        trace_id: Identifier to bind. ``None`` → ``new_trace_id()``.
    """
    tid = trace_id or new_trace_id()
    token = TRACE_ID.set(tid)
    structlog.contextvars.bind_contextvars(trace_id=tid)
    try:
        yield tid
    finally:
        structlog.contextvars.unbind_contextvars("trace_id")
        TRACE_ID.reset(token)
