"""Plan 8 T4 — Sentry event filter primitives (pure functions).

Decoupled from obs.sentry so the filter logic is unit-testable without
spinning up the real sentry_sdk client. init_sentry() builds and passes
these into sentry_sdk.init().
"""
from __future__ import annotations

from typing import Any, Callable

# Set of stripe error class names whose 4xx variants we never want to ship to Sentry
_STRIPE_4XX_CLASSES = {
    "InvalidRequestError",   # bad params
    "CardError",             # user card failed
    "AuthenticationError",   # bad API key
    "PermissionError",
    "IdempotencyError",
}

# Health / metrics paths sampled at 0
_ZERO_SAMPLE_PATHS = {"/health", "/metrics", "/ready"}

# Sensitive paths always fully sampled
_FULL_SAMPLE_PATHS = {"/api/v1/billing/webhook"}


class ExpectedDriftAlert(Exception):
    """Raised intentionally by drift detection to fan out an alert.

    Sentry should not record it — Alertmanager / TG / Slack handle it.
    """


def _exception_class_name(hint: dict) -> str | None:
    info = hint.get("exc_info")
    if not info:
        return None
    exc_type = info[0]
    return getattr(exc_type, "__name__", None)


def _exception_status_code(hint: dict) -> int | None:
    info = hint.get("exc_info")
    if not info:
        return None
    exc = info[1]
    # stripe SDK exposes http_status on its errors; httpx puts it on .response.status_code
    if hasattr(exc, "http_status"):
        return getattr(exc, "http_status")
    response = getattr(exc, "response", None)
    if response is not None and hasattr(response, "status_code"):
        return getattr(response, "status_code")
    return None


def build_before_send() -> Callable[[dict, dict], dict | None]:
    """Construct the Sentry before_send callback.

    Returns event unchanged when not filtered; returns None to drop.
    """

    def _before_send(event: dict, hint: dict) -> dict | None:
        cls = _exception_class_name(hint)
        if cls == "ExpectedDriftAlert":
            return None
        if cls in _STRIPE_4XX_CLASSES:
            return None
        status = _exception_status_code(hint)
        if status is not None and 400 <= status < 500:
            return None
        return event

    return _before_send


def build_traces_sampler(baseline: float = 0.1) -> Callable[[dict], float]:
    """Construct the Sentry traces_sampler callback.

    /health, /metrics, /ready → 0%; /billing/webhook → 100%; otherwise baseline.
    """

    def _sampler(ctx: dict[str, Any]) -> float:
        tx = ctx.get("transaction_context") or {}
        name = tx.get("name", "")
        if name in _ZERO_SAMPLE_PATHS:
            return 0.0
        if name in _FULL_SAMPLE_PATHS:
            return 1.0
        return baseline

    return _sampler
