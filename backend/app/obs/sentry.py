"""Plan 8 T3 — Sentry SDK init helper.

DSN-driven init:
- ``SENTRY_DSN`` env empty → no-op (warning log), returns False
- ``ENV=test`` → no-op (avoid noise during pytest)
- Otherwise initializes sentry_sdk with the appropriate integrations.

T4 will add ``before_send`` filtering; this Task is "minimal viable
init" only.
"""
from __future__ import annotations

import os

import sentry_sdk
import structlog
from sentry_sdk.integrations import Integration

log = structlog.get_logger().bind(component="obs.sentry")


def init_sentry(
    *,
    service: str,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.0,
    extra_integrations: list[Integration] | None = None,
) -> bool:
    """Initialise Sentry SDK; fail-soft when DSN is missing.

    Returns True if init succeeded, False if skipped (no DSN, or ENV=test).
    """
    env = environment or os.getenv("ENV", "dev")
    if env == "test":
        return False

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        log.warning("sentry_dsn_missing", service=service, environment=env)
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release=release or os.getenv("OBS_VERSION", "unknown"),
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,
        integrations=extra_integrations or [],
    )
    sentry_sdk.set_tag("service", service)
    log.info(
        "sentry_initialized",
        service=service,
        environment=env,
        traces_sample_rate=traces_sample_rate,
    )
    return True
