"""Schemas for the live watchlist indicator panel — A2 (scoped v1).

POST /api/v1/watchlist/indicators takes a list of symbols and returns, per
symbol, the current live price (reusing the portfolio live-price fetcher)
plus a handful of computed indicators (RSI, MA cross state, % distance from
the MA) derived from the same daily-close history the /indicators endpoints
read. No new indicator math lives here — the values come from the existing
TA-Lib wrappers via ``app.modules.watchlist.live_indicators``.

Why a dedicated batch endpoint instead of N calls to /indicators/calculate:
  - the panel polls every few seconds for the whole watchlist; one batched
    request keeps the outbound RPS low and lets the live-price fetcher's TTL
    cache do its job.
  - the panel needs price + change + indicators in one shape so the frontend
    renders a single coherent row without stitching responses together.

Decimal-as-string contract: every numeric money/indicator field is serialised
as ``str`` (matching the rest of the API) so the frontend's ``Number()``
coercion path is uniform. Missing data (no price feed, insufficient history)
is ``None`` → renders as an em-dash, never a fabricated zero.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel


class WatchlistIndicatorRequest(StrictModel):
    """Batch request for the live watchlist panel.

    ``symbols`` is bounded (1..50) so a single poll can't fan out into an
    unbounded number of price-feed + DB lookups. The frontend only ever
    sends the symbols currently on the user's watchlist, which is itself
    tier-capped well below this ceiling.
    """

    symbols: list[str] = Field(..., min_length=1, max_length=50)


class WatchlistLiveIndicator(BaseModel):
    """One symbol's live snapshot for the panel.

    Field contract (all numerics are Decimal-as-string or ``None``):
      - ``last_price`` / ``prev_close`` — from the live-price fetcher; ``None``
        when no feed/data is available for the symbol.
      - ``change`` / ``change_percent`` — derived from last vs prev close;
        ``None`` when either side is missing.
      - ``rsi`` — latest RSI(14) value, ``None`` during the warmup window or
        when there is no price history.
      - ``ma_short`` / ``ma_long`` — latest short/long SMA values.
      - ``ma_cross`` — ``"golden"`` (short > long), ``"death"`` (short < long),
        ``"flat"`` (equal), or ``None`` when either MA is unavailable.
      - ``pct_from_ma_long`` — percent distance of last price from the long MA;
        positive = price above MA. ``None`` when inputs are missing.
    """

    symbol: str
    last_price: str | None = None
    prev_close: str | None = None
    change: str | None = None
    change_percent: str | None = None
    rsi: str | None = None
    ma_short: str | None = None
    ma_long: str | None = None
    ma_cross: str | None = None
    pct_from_ma_long: str | None = None


class WatchlistIndicatorResponse(BaseModel):
    """Envelope: one entry per requested symbol, in request order.

    Symbols with no data still appear (with ``None`` fields) so the frontend
    can render a stable row per watched symbol rather than dropping rows.
    """

    items: list[WatchlistLiveIndicator]
