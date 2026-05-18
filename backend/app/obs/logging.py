"""Plan 8 T1 — structlog config.

Two output modes:
- ``ENV in {dev, test}`` → ``structlog.dev.ConsoleRenderer(colors=True)``
- otherwise → ``structlog.processors.JSONRenderer()`` (production)

Common fields injected into every log line: timestamp / level / event /
service / environment / component / version. ``trace_id`` is merged from
ContextVar by T2 (added separately) — already wired via
``merge_contextvars`` processor.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

_CONFIGURED = False


def configure_logging(
    *,
    service: str,
    environment: str | None = None,
    version: str | None = None,
    log_level: str = "INFO",
) -> None:
    """Configure structlog globally for this process.

    Safe to call multiple times (idempotent re-configure each time);
    designed to be invoked exactly once at application startup.
    """
    global _CONFIGURED
    env = environment or os.getenv("ENV", "dev")
    ver = version or os.getenv("OBS_VERSION", "unknown")

    # Bind common static fields once via contextvars so every record carries them.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        service=service,
        environment=env,
        version=ver,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env in {"dev", "test"}:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    _CONFIGURED = True


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger pre-bound with the caller's component name."""
    return structlog.get_logger().bind(component=component)
