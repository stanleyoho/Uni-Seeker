"""FastAPI dependencies specific to /holdings endpoints.

Provides `get_live_price_fetcher()` so that the position / summary
endpoints can be unit-tested with a `MockLivePriceFetcher` via
`app.dependency_overrides`. Production wiring (Phase 2, spec §8.4 / §8.5):

    CompositeLivePriceFetcher(
        primary   = YFinanceLivePriceFetcher(ttl=60),
        secondary = CachedDailyCloseLivePriceFetcher(async_session, ttl=300),
    )

The composite tries yfinance first (intraday freshness) and falls back to
the DB-backed daily-close path whenever yfinance is rate-limited / unreachable
or simply has no data for a symbol. TTLs:
  - 60s for yfinance  → bounds outbound RPS while still letting intraday
    refresh on each subsequent request inside the cache window.
  - 300s for DB cache → DB hit is cheap-ish but daily-close numbers only
    change once a day; 5 minutes is a comfortable cushion.
"""
from __future__ import annotations

from app.database import async_session
from app.modules.portfolio.live_price_fetcher import (
    CachedDailyCloseLivePriceFetcher,
    CompositeLivePriceFetcher,
    LivePriceFetcher,
    YFinanceLivePriceFetcher,
)


def get_live_price_fetcher() -> LivePriceFetcher:
    """Default production fetcher — yfinance with daily-close fallback.

    Tests should `app.dependency_overrides[get_live_price_fetcher]
    = lambda: MockLivePriceFetcher({...})` to inject deterministic
    quotes (spec §8.3 / §10.3); the override is honoured regardless
    of how the production path is wired, so this composition is
    transparent to the existing service / integration test suites.
    """
    return CompositeLivePriceFetcher(
        primary=YFinanceLivePriceFetcher(ttl_seconds=60),
        secondary=CachedDailyCloseLivePriceFetcher(
            async_session, ttl_seconds=300
        ),
    )


__all__ = ["get_live_price_fetcher"]
