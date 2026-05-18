"""Plan 8 T3/T4 — Sentry SDK init helper.

DSN-driven init:
- ``SENTRY_DSN`` env empty → no-op (warning log), returns False
- ``ENV=test`` → no-op (avoid noise during pytest)
- Otherwise initializes sentry_sdk with ``before_send`` event filtering
  and ``traces_sampler`` per-path sampling (Plan 8 T4).
"""
from __future__ import annotations

import os

import sentry_sdk
import structlog
from sentry_sdk.integrations import Integration

from app.obs._sentry_filters import build_before_send, build_traces_sampler

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

    ``traces_sample_rate`` is now the baseline fed into
    :func:`build_traces_sampler`; per-path overrides (e.g. /health → 0,
    /billing/webhook → 1) are applied by the sampler callback.

    Returns True if init succeeded, False if skipped (no DSN, or ENV=test).
    """
    env = environment or os.getenv("ENV", "dev")
    if env == "test":
        return False

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        log.warning("sentry_dsn_missing", service=service, environment=env)
        return False

    _before_send = build_before_send()
    _traces_sampler = build_traces_sampler(baseline=traces_sample_rate)

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release=release or os.getenv("OBS_VERSION", "unknown"),
        traces_sampler=_traces_sampler,
        before_send=_before_send,
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
