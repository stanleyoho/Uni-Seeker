"""Sentry event filter primitives — thin wrapper over observability-core.

Hosts Uni-Seeker's repo-specific ``ExpectedDriftAlertError`` exception class
and re-exports the package's filter builders with Uni-Seeker defaults
pre-applied (Stripe 4xx drop + ``ExpectedDriftAlertError`` drop +
``/api/v1/billing/webhook`` full sample, on top of the package's own
zero-sample defaults for ``/health`` ``/metrics`` ``/ready``).

Since 2026-05-24 Stage 2 migration the actual filter logic lives in
``observability_core._sentry_filters`` — callers (production wiring +
unit tests) keep using ``from app.obs._sentry_filters import ...``.
"""

from __future__ import annotations

from collections.abc import Callable

from observability_core._sentry_filters import (
    build_before_send as _core_build_before_send,
)
from observability_core._sentry_filters import (
    build_traces_sampler as _core_build_traces_sampler,
)

# Uni-Seeker-specific path policy — Stripe webhook is fully traced.
_FULL_SAMPLE_PATHS = frozenset({"/api/v1/billing/webhook"})


class ExpectedDriftAlertError(Exception):
    """Raised intentionally by drift detection to fan out an alert.

    Sentry should not record it — Alertmanager / TG / Slack handle it.
    Wired into :func:`build_before_send` via the package's
    ``drop_exception_classes`` kwarg so it is dropped by isinstance check
    (subclasses included).
    """


def build_before_send() -> Callable[[dict, dict], dict | None]:
    """Construct the Sentry ``before_send`` callback with Uni-Seeker policy.

    Drops:
    - Stripe 4xx (package default — InvalidRequestError, CardError,
      AuthenticationError, PermissionError, IdempotencyError)
    - any ``ExpectedDriftAlertError`` (and subclasses)
    - any other exception with HTTP status 400 <= s < 500

    Returns event unchanged when not filtered; returns None to drop.
    """
    return _core_build_before_send(
        drop_exception_classes=(ExpectedDriftAlertError,),
    )


def build_traces_sampler(baseline: float = 0.1) -> Callable[[dict], float]:
    """Construct the Sentry ``traces_sampler`` callback with Uni-Seeker policy.

    - ``/health``, ``/metrics``, ``/ready`` → 0% (package default)
    - ``/api/v1/billing/webhook`` → 100% (Uni-Seeker override)
    - otherwise → ``baseline``
    """
    return _core_build_traces_sampler(
        baseline=baseline,
        full_sample_paths=_FULL_SAMPLE_PATHS,
    )


__all__ = [
    "ExpectedDriftAlertError",
    "build_before_send",
    "build_traces_sampler",
]
