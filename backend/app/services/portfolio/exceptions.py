"""Domain exceptions raised by portfolio services.

Spec §9 双保险: service-level tier assertions raise domain exceptions
(NOT `HTTPException`). The API layer catches and translates to HTTP
status codes. This keeps services callable from non-HTTP contexts
(e.g. CLI tools, batch jobs, tests) without importing FastAPI.
"""

from __future__ import annotations


class PortfolioServiceError(Exception):
    """Base class for all portfolio service-level domain errors."""


class PortfolioAccountNotFound(PortfolioServiceError):
    """Account id does not exist OR is not owned by the requesting user.

    Service layer collapses 404 and 403 to the same signal on purpose —
    leaking "exists but not yours" is itself an information disclosure.
    API layer translates to 404.
    """


class PortfolioTradeNotFound(PortfolioServiceError):
    """Trade id does not exist OR its parent account is not owned by
    the requesting user. Same 404/403 collapse as above."""


class TierLimitExceeded(PortfolioServiceError):
    """User's tier numeric quota would be exceeded by this operation.

    `limit_key` is the YAML key (e.g. ``max_accounts``,
    ``max_trades_per_month``, ``max_positions``); ``current`` and
    ``limit`` are the snapshot at decision time. API layer translates
    to 403 with ``detail = "limit_exceeded:{limit_key}"``.
    """

    def __init__(self, limit_key: str, current: int, limit: int) -> None:
        self.limit_key = limit_key
        self.current = current
        self.limit = limit
        super().__init__(f"tier limit '{limit_key}' exceeded: {current} >= {limit}")


class TierFeatureUnavailable(PortfolioServiceError):
    """User's tier does not have the requested boolean feature flag.

    API layer translates to 403 with ``detail = "feature_unavailable:{feature}"``.
    """

    def __init__(self, feature: str) -> None:
        self.feature = feature
        super().__init__(f"tier feature '{feature}' is unavailable")


class InsufficientShares(PortfolioServiceError):
    """SELL trade quantity exceeds the open-lot total for the symbol.

    Wraps `app.modules.trade_journal.fifo_engine.InsufficientSharesError`
    so the API layer can catch a single portfolio-namespaced exception
    type without importing the trade journal module."""


__all__ = [
    "InsufficientShares",
    "PortfolioAccountNotFound",
    "PortfolioServiceError",
    "PortfolioTradeNotFound",
    "TierFeatureUnavailable",
    "TierLimitExceeded",
]
