"""Unified ``MarketDataProvider`` abstraction (A2 audit item).

Why this exists
===============
Market data is fetched from several upstreams with *ad-hoc, divergent*
call signatures:

* ``YFinanceProvider`` — ``fetch_daily_prices(symbol)`` (last 5 days) and
  ``fetch_history(symbol, period)`` (period string like ``"1y"``)
* ``TWSEProvider`` / ``TPEXProvider`` — ``fetch_daily_prices(symbol)``
  (a *market-wide snapshot* filtered to one symbol; no date range)
* ``FinMindStockProvider`` — ``fetch_daily_prices(stock_id, start, end)``
  (date range, *bare* stock_id, no suffix)

Callers therefore have to know which concrete source they are talking to
and translate arguments themselves. This module defines one interface so a
caller can resolve a provider for a symbol and call a *uniform* surface:

    provider = registry.for_symbol("2330.TW")
    bars = await provider.get_daily_ohlcv("2330.TW", start, end)
    quote = await provider.get_quote("2330.TW")

It reuses the existing normalized :class:`StockPriceData` dataclass from
``app.modules.price_updater.base`` rather than introducing a parallel
shape — the unified part is the *interface*, not the payload.

Layering
========
This lives under ``app.services`` (not ``app.modules``) on purpose: the
adapters import the concrete fetchers from ``app.modules.*``, and the
import-linter contracts allow ``services -> modules`` (the forbidden edge
is ``modules -> api``). Placing the protocol in ``app.modules`` would be
fine too, but the *registry* wires several modules together, which is a
service-composition concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.modules.price_updater.base import StockPriceData


@dataclass(frozen=True)
class StockQuote:
    """A single latest-bar quote for a symbol.

    Distinct from :class:`StockPriceData` (which represents one historical
    daily bar): a quote is the *most recent* observation and is what a
    caller wants for "what is X trading at right now". Reuses the same
    Decimal-typed OHLC fields for consistency.
    """

    symbol: str
    market: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change: Decimal = Decimal("0")
    change_percent: Decimal = Decimal("0")
    name: str = ""

    @classmethod
    def from_price_data(cls, p: StockPriceData) -> StockQuote:
        """Build a quote from a normalized :class:`StockPriceData` bar."""
        return cls(
            symbol=p.symbol,
            market=p.market,
            date=p.date,
            open=p.open,
            high=p.high,
            low=p.low,
            close=p.close,
            volume=p.volume,
            change=p.change,
            change_percent=p.change_percent,
            name=p.name,
        )


@runtime_checkable
class MarketDataProvider(Protocol):
    """Unified read interface over a single market-data source.

    Implementations are *thin adapters* over the existing concrete
    providers — they translate the uniform arguments below into whatever
    the underlying fetcher expects, and normalize the result to
    :class:`StockPriceData` / :class:`StockQuote`.

    The ``@runtime_checkable`` decorator lets the conformance test assert
    ``isinstance(adapter, MarketDataProvider)`` for every adapter.
    """

    @property
    def market_code(self) -> str:
        """Stable identifier for this source's primary market.

        One of the ``app.models.enums.Market`` values, e.g.
        ``"TW_TWSE"``, ``"TW_TPEX"``, ``"US_NASDAQ"``. Used for logging
        and for the registry's capability table.
        """
        ...

    def supports(self, symbol: str) -> bool:
        """Return whether this provider can serve ``symbol``.

        The capability discriminator used by the registry to route a
        symbol. Pure / synchronous — no network.
        """
        ...

    async def get_daily_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[StockPriceData]:
        """Fetch daily OHLCV bars for ``symbol`` in ``[start, end]``.

        Returns normalized :class:`StockPriceData`, oldest-to-newest where
        the upstream provides ordering. Sources that only expose a
        market-wide *snapshot* (TWSE/TPEX OpenAPI) return at most the
        single latest bar regardless of the requested range; that is
        documented per-adapter.
        """
        ...

    async def get_quote(self, symbol: str) -> StockQuote | None:
        """Fetch the latest single quote for ``symbol``.

        Returns ``None`` when the upstream has no data for the symbol.
        """
        ...
