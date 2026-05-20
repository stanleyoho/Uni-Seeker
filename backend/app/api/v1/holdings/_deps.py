"""FastAPI dependencies specific to /holdings endpoints.

Provides `get_live_price_fetcher()` so that the position / summary
endpoints can be unit-tested with a `MockLivePriceFetcher` via
`app.dependency_overrides`. Production wires
`DailyCloseLivePriceFetcher` against the global async sessionmaker.
"""
from __future__ import annotations

from app.database import async_session
from app.modules.portfolio.live_price_fetcher import (
    DailyCloseLivePriceFetcher,
    LivePriceFetcher,
)


def get_live_price_fetcher() -> LivePriceFetcher:
    """Default production fetcher.

    Tests should `app.dependency_overrides[get_live_price_fetcher]
    = lambda: MockLivePriceFetcher({...})` to inject deterministic
    quotes (spec §8.3 / §10.3).
    """
    return DailyCloseLivePriceFetcher(async_session)


__all__ = ["get_live_price_fetcher"]
