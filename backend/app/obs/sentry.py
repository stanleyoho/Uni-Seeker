"""Sentry SDK init helper — thin wrapper over observability-core.

Translates Uni-Seeker's repo-specific filter policy (Stripe 4xx drop +
``ExpectedDriftAlertError`` drop + ``/api/v1/billing/webhook`` full sample)
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

import sentry_sdk
from observability_core.sentry import init_sentry as _core_init_sentry

from app.obs._sentry_filters import ExpectedDriftAlertError

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

    - ``drop_exception_classes=(ExpectedDriftAlertError,)`` — drift alerts are
      a notification channel, not a bug, and must never reach Sentry.
    - ``full_sample_paths=("/api/v1/billing/webhook",)`` — Stripe webhook
      is sensitive enough to always be fully traced.
    - Stripe 4xx drop + ``/health`` ``/metrics`` ``/ready`` zero-sample
      come from the package defaults (see
      ``observability_core._sentry_filters.DEFAULT_DROP_4XX_CLASSES`` /
      ``DEFAULT_ZERO_SAMPLE_PATHS``).

    Returns True if init succeeded, False if skipped (no DSN, or ENV=test).
    """
    ok = bool(
        _core_init_sentry(
            service=service,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            extra_integrations=extra_integrations,
            drop_exception_classes=(ExpectedDriftAlertError,),
            full_sample_paths=_FULL_SAMPLE_PATHS,
        )
    )
    if ok:
        # observability-core already tags `service` and passes
        # environment/release into ``sentry_sdk.init`` (Sentry surfaces both
        # as searchable facets). Add the repo-specific `component` tag so
        # backend events are filterable apart from any future worker/cron
        # process that shares the same DSN.
        sentry_sdk.set_tag("component", "backend")
    return ok


def set_task_tags(**tags: str) -> None:
    """Set per-task Sentry tags on the current scope (fail-soft).

    Used by background tasks (e.g. the sync scheduler) to attach the dataset /
    task name to the active scope so an exception captured during that task is
    searchable by ``task`` / ``dataset`` in Sentry. When Sentry is not
    initialised (tests, no DSN) ``sentry_sdk.set_tag`` is a cheap no-op, so
    callers need no guard. Kept deliberately thin — no scope push/pop — because
    the sync scheduler runs one task at a time per worker.
    """
    for key, value in tags.items():
        sentry_sdk.set_tag(key, value)
