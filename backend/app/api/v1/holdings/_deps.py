"""FastAPI dependencies specific to /holdings endpoints.

Provides `get_live_price_fetcher()` and the Phase 4+ `get_fx_fetcher()` /
`get_fx_service()` so endpoints can be unit-tested with mocks via
`app.dependency_overrides`. Production wiring:

    CompositeLivePriceFetcher(
        primary   = YFinanceLivePriceFetcher(ttl=60),
        secondary = CachedDailyCloseLivePriceFetcher(async_session, ttl=300),
    )

    FxService(
        db        = request-scoped AsyncSession,
        fetcher   = process-singleton YFinanceFxFetcher(ttl=3600),
    )

The composite tries yfinance first (intraday freshness) and falls back to
the DB-backed daily-close path whenever yfinance is rate-limited / unreachable
or simply has no data for a symbol. TTLs:
  - 60s for yfinance prices  → bounds outbound RPS while still letting
    intraday refresh on each subsequent request inside the cache window.
  - 300s for DB price cache  → daily-close numbers change once a day.
  - 3600s for FX             → FX is slow-moving for portfolio KPI purposes.

`_FX_FETCHER` is module-level so its TTL cache outlives a single request
(no point caching a USD→TWD rate if a fresh fetcher is built per request).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.database import async_session
from app.modules.portfolio.fx_fetcher import YFinanceFxFetcher
from app.modules.portfolio.live_price_fetcher import (
    CachedDailyCloseLivePriceFetcher,
    CompositeLivePriceFetcher,
    LivePriceFetcher,
    YFinanceLivePriceFetcher,
)
from app.services.portfolio.fx_service import FxService

# Process-singleton fetcher so cache survives across requests.
_FX_FETCHER: YFinanceFxFetcher | None = None


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


def get_fx_fetcher() -> YFinanceFxFetcher:
    """Process-singleton FX fetcher (shared TTL cache across requests)."""
    global _FX_FETCHER
    if _FX_FETCHER is None:
        _FX_FETCHER = YFinanceFxFetcher(ttl_seconds=3600)
    return _FX_FETCHER


def get_fx_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    fetcher: Annotated[YFinanceFxFetcher, Depends(get_fx_fetcher)],
) -> FxService:
    """Per-request FxService wiring (request-scoped DB + singleton fetcher)."""
    return FxService(db=db, fetcher=fetcher)


__all__ = [
    "get_live_price_fetcher",
    "get_fx_fetcher",
    "get_fx_service",
]
