"""Centralised HTTPException ``detail`` strings for /holdings/*.

Spec §9.5 + frontend contract: every 4xx body's ``message`` field
(see `app/middleware/error_handler.py:13`) is asserted on by the
frontend. Define the strings ONCE here so a typo doesn't drift between
sub-routers.

Format conventions:
    * ``feature_unavailable:{feature}`` — 403 raised when the user's
      tier lacks a boolean feature flag (mirrors
      `app.modules.billing.tier_limits.tier_guard`).
    * ``limit_exceeded:{limit_key}`` — 403 raised when a numeric quota
      would be exceeded.
    * other identifiers are flat snake_case nouns.
"""

from __future__ import annotations

ACCOUNT_NOT_FOUND = "portfolio_account_not_found"
TRADE_NOT_FOUND = "portfolio_trade_not_found"
DIVIDEND_NOT_FOUND = "portfolio_dividend_not_found"
INSUFFICIENT_SHARES = "insufficient_shares"
INVALID_TRADE_INPUT = "invalid_trade_input"
INVALID_DIVIDEND_INPUT = "invalid_dividend_input"
IMMUTABLE_DIVIDEND_FIELD = "immutable_dividend_field"
INVALID_CSV_FORMAT = "invalid_csv_format"
CSV_TOO_LARGE = "csv_too_large"
IMPORT_PARTIAL_FAILURE = "import_partial_failure"
EXPORT_NO_DATA = "export_no_data"
ALERT_RULE_NOT_FOUND = "alert_rule_not_found"
INVALID_ALERT_RULE = "invalid_alert_rule"


def limit_exceeded(limit_key: str) -> str:
    """Compose the ``limit_exceeded:{key}`` 403 detail string."""
    return f"limit_exceeded:{limit_key}"


def feature_unavailable(feature: str) -> str:
    """Compose the ``feature_unavailable:{feature}`` 403 detail string."""
    return f"feature_unavailable:{feature}"


__all__ = [
    "ACCOUNT_NOT_FOUND",
    "ALERT_RULE_NOT_FOUND",
    "CSV_TOO_LARGE",
    "DIVIDEND_NOT_FOUND",
    "EXPORT_NO_DATA",
    "IMMUTABLE_DIVIDEND_FIELD",
    "IMPORT_PARTIAL_FAILURE",
    "INSUFFICIENT_SHARES",
    "INVALID_ALERT_RULE",
    "INVALID_CSV_FORMAT",
    "INVALID_DIVIDEND_INPUT",
    "INVALID_TRADE_INPUT",
    "TRADE_NOT_FOUND",
    "feature_unavailable",
    "limit_exceeded",
]
