"""Sentry SDK init helper — thin wrapper over observability-core.

Translates Uni-Seeker's repo-specific filter policy (Stripe 4xx drop +
``ExpectedDriftAlert`` drop + ``/api/v1/billing/webhook`` full sample)
to generic kwargs of :func:`observability_core.sentry.init_sentry`,
preserving the existing call-site contract
(``from app.obs.sentry import init_sentry`` with the same kwargs).

Since 2026-05-24 Stage 2 migration the actual ``sentry_sdk.init`` /
filter wiring lives in observability-core. The hardcoded policy that
used to live in ``app.obs._sentry_filters`` is now supplied here as
init kwargs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from observability_core.sentry import init_sentry as _core_init_sentry

from app.obs._sentry_filters import ExpectedDriftAlert

if TYPE_CHECKING:
    from sentry_sdk.integrations import Integration

# Sensitive paths always fully sampled. Repo-specific (Stripe webhook
# under /api/v1/billing/webhook); the package default for zero-sample
# paths (/health /metrics /ready) is reused unchanged.
_FULL_SAMPLE_PATHS = frozenset({"/api/v1/billing/webhook"})


def init_sentry(
    *,
    service: str,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.0,
    extra_integrations: list[Integration] | None = None,
) -> bool:
    """Initialise Sentry SDK for Uni-Seeker; fail-soft when DSN is missing.

    Wraps :func:`observability_core.sentry.init_sentry` with Uni-Seeker's
    filter policy:

    - ``drop_exception_classes=(ExpectedDriftAlert,)`` — drift alerts are
      a notification channel, not a bug, and must never reach Sentry.
    - ``full_sample_paths=("/api/v1/billing/webhook",)`` — Stripe webhook
      is sensitive enough to always be fully traced.
    - Stripe 4xx drop + ``/health`` ``/metrics`` ``/ready`` zero-sample
      come from the package defaults (see
      ``observability_core._sentry_filters.DEFAULT_DROP_4XX_CLASSES`` /
      ``DEFAULT_ZERO_SAMPLE_PATHS``).

    Returns True if init succeeded, False if skipped (no DSN, or ENV=test).
    """
    return _core_init_sentry(
        service=service,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        extra_integrations=extra_integrations,
        drop_exception_classes=(ExpectedDriftAlert,),
        full_sample_paths=_FULL_SAMPLE_PATHS,
    )
