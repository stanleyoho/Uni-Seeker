"""Service-side structlog adopter — thin wrapper over observability-core.

Uni-Seeker is a SERVICE: ``configure_logging()`` is called once at app
startup (see ``app.main.lifespan``), then ``get_logger("module.name")``
is used everywhere. No ``library=`` tag (services own their pipeline).

Since 2026-05-24 Stage 2 migration the actual implementation lives in
``observability_core.logging`` (v0.2.0+). This module preserves the
existing ``from app.obs.logging import configure_logging, get_logger``
call sites without modification.
"""

from __future__ import annotations

from typing import Any

from observability_core.logging import configure_logging as _core_configure_logging
from observability_core.logging import get_logger as _core_get_logger


def configure_logging(
    *,
    service: str,
    environment: str | None = None,
    version: str | None = None,
    log_level: str = "INFO",
) -> None:
    """Configure structlog globally for this process.

    Service-side initialiser. Safe to call multiple times (idempotent
    re-configure); designed to be invoked exactly once at application
    startup.
    """
    _core_configure_logging(
        service=service,
        environment=environment,
        version=version,
        log_level=log_level,
    )


def get_logger(component: str) -> Any:
    """Return a structlog logger pre-bound with the caller's component name.

    Service-side: no ``library=`` tag — Uni-Seeker owns the structlog
    pipeline (via :func:`configure_logging`), unlike library packages
    such as AAE.
    """
    return _core_get_logger(component)
