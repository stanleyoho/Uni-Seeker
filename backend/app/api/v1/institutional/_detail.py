"""Centralised HTTPException ``detail`` strings for /api/v1/institutional/*.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5. Mirrors the convention from `app.api.v1.holdings._detail`: every
4xx body's ``message`` field (see `app/middleware/error_handler.py`) is
asserted on by the frontend; the strings are defined ONCE here so a
typo doesn't drift between sub-routers.

Format conventions:
    * ``feature_unavailable:{feature}`` — 403 raised when the user's
      tier lacks a boolean feature flag (mirrors
      `app.modules.billing.tier_limits.tier_guard`).
    * ``limit_exceeded:{limit_key}`` — 403 raised when a numeric quota
      would be exceeded.
    * other identifiers are flat snake_case nouns.
"""

from __future__ import annotations

F13_FILER_NOT_FOUND = "f13_filer_not_found"
F13_FILING_NOT_FOUND = "f13_filing_not_found"
F13_SUBSCRIPTION_EXISTS = "f13_subscription_exists"
F13_REFRESH_IN_FLIGHT = "f13_refresh_in_flight"
F13_INVALID_INPUT = "f13_invalid_input"
F13_EDGAR_ERROR = "f13_edgar_error"
F13_STOCK_NOT_FOUND = "f13_stock_not_found"


def limit_exceeded(limit_key: str) -> str:
    """Compose the ``limit_exceeded:{key}`` 403 detail string.

    Re-used across portfolio + institutional modules so the frontend's
    single error mapper handles both.
    """
    return f"limit_exceeded:{limit_key}"


def feature_unavailable(feature: str) -> str:
    """Compose the ``feature_unavailable:{feature}`` 403 detail string."""
    return f"feature_unavailable:{feature}"


__all__ = [
    "F13_EDGAR_ERROR",
    "F13_FILER_NOT_FOUND",
    "F13_FILING_NOT_FOUND",
    "F13_INVALID_INPUT",
    "F13_REFRESH_IN_FLIGHT",
    "F13_STOCK_NOT_FOUND",
    "F13_SUBSCRIPTION_EXISTS",
    "feature_unavailable",
    "limit_exceeded",
]
