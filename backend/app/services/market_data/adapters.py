"""Thin adapters wrapping the existing concrete providers.

Each adapter exposes the uniform :class:`MarketDataProvider` surface and
delegates to the *existing* fetch code in ``app.modules.*`` — no fetch
logic is reimplemented here. The adapters only:

1. translate the uniform ``(symbol, start, end)`` arguments into what the
   underlying provider expects, and
2. filter / shape the result into the common return types.

Behaviour of the underlying providers is unchanged; existing direct
callers (e.g. ``PriceUpdater``) keep using them as before.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx

from app.modules.finmind.stock_provider import FinMindStockProvider
from app.modules.price_updater.base import StockPriceData
from app.modules.price_updater.tpex import TPEXProvider
from app.modules.price_updater.twse import TWSEProvider
from app.modules.price_updater.yfinance_provider import YFinanceProvider
from app.services.market_data.base import MarketDataProvider, StockQuote
from app.services.market_data.symbols import (
    MarketClass,
    classify_symbol,
    to_bare_tw_code,
)


def _latest(prices: list[StockPriceData]) -> StockPriceData | None:
    """Return the bar with the most recent date, or ``None`` if empty."""
    if not prices:
        return None
    return max(prices, key=lambda p: p.date)


def _in_range(prices: list[StockPriceData], start: date, end: date) -> list[StockPriceData]:
    """Keep only bars whose date is within ``[start, end]`` inclusive."""
    return [p for p in prices if start <= p.date <= end]


def _quote_window_start() -> str:
    """ISO start date covering enough days to capture the latest TW bar.

    FinMind requires a ``start_date``; a quote wants only the most recent
    bar, so we ask for a short trailing window (10 calendar days covers
    weekends + a holiday) and take the latest.
    """
    return (date.today() - timedelta(days=10)).isoformat()


class YFinanceMarketDataAdapter:
    """Adapter for US equities served by yfinance.

    ``get_daily_ohlcv`` uses the existing ``fetch_history`` (period-based)
    and filters to the requested date window — yfinance has no native
    start/end on the wrapped call, so we fetch a covering period and trim.
    """

    def __init__(self, provider: YFinanceProvider | None = None) -> None:
        self._provider = provider or YFinanceProvider()

    @property
    def market_code(self) -> str:
        return self._provider.market

    def supports(self, symbol: str) -> bool:
        return classify_symbol(symbol) is MarketClass.US

    async def get_daily_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[StockPriceData]:
        # Pick the smallest covering period for the requested window so we
        # do not over-fetch a decade for a 5-day request.
        span_days = (end - start).days
        period = self._period_for_span(span_days)
        prices = await self._provider.fetch_history(symbol, period)
        return _in_range(prices, start, end)

    async def get_quote(self, symbol: str) -> StockQuote | None:
        prices = await self._provider.fetch_daily_prices(symbol)
        latest = _latest(prices)
        return StockQuote.from_price_data(latest) if latest else None

    @staticmethod
    def _period_for_span(span_days: int) -> str:
        if span_days <= 5:
            return "5d"
        if span_days <= 31:
            return "1mo"
        if span_days <= 93:
            return "3mo"
        if span_days <= 186:
            return "6mo"
        if span_days <= 366:
            return "1y"
        if span_days <= 366 * 2:
            return "2y"
        if span_days <= 366 * 5:
            return "5y"
        return "max"


class _TWOpenAPIAdapterBase:
    """Shared logic for the TWSE / TPEX OpenAPI snapshot adapters.

    These upstreams expose only a *current-day market-wide snapshot* — no
    historical range. So ``get_daily_ohlcv`` returns the snapshot's single
    latest bar *iff* its date falls inside the requested window, and
    ``get_quote`` returns that bar directly. This is faithful to the
    existing behaviour (``fetch_daily_prices`` already returns one bar per
    symbol for "today").
    """

    _market_class: MarketClass

    def __init__(self, provider: TWSEProvider | TPEXProvider) -> None:
        self._provider = provider

    @property
    def market_code(self) -> str:
        return self._provider.market

    def supports(self, symbol: str) -> bool:
        cls = classify_symbol(symbol)
        # A bare TW code (MarketClass.TW) is not assigned to a specific
        # board from the string alone, so the TWSE/TPEX snapshot adapters
        # only claim their *explicitly suffixed* symbols.
        return cls is self._market_class

    def _underlying_symbol(self, symbol: str) -> str:
        # The TW OpenAPI snapshot filters on the *bare* code (it builds the
        # suffix itself), so strip ".TW"/".TWO" before passing through.
        return to_bare_tw_code(symbol)

    async def get_daily_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[StockPriceData]:
        prices = await self._provider.fetch_daily_prices(self._underlying_symbol(symbol))
        return _in_range(prices, start, end)

    async def get_quote(self, symbol: str) -> StockQuote | None:
        prices = await self._provider.fetch_daily_prices(self._underlying_symbol(symbol))
        latest = _latest(prices)
        return StockQuote.from_price_data(latest) if latest else None


class TWSEMarketDataAdapter(_TWOpenAPIAdapterBase):
    """Adapter for the TWSE (Taiwan main board) OpenAPI snapshot."""

    _market_class = MarketClass.TW_TWSE

    def __init__(
        self, provider: TWSEProvider | None = None, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if provider is None:
            if client is None:
                raise ValueError("TWSEMarketDataAdapter requires a provider or an httpx client")
            provider = TWSEProvider(client=client)
        super().__init__(provider)


class TPEXMarketDataAdapter(_TWOpenAPIAdapterBase):
    """Adapter for the TPEX (Taiwan OTC) OpenAPI snapshot."""

    _market_class = MarketClass.TW_TPEX

    def __init__(
        self, provider: TPEXProvider | None = None, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if provider is None:
            if client is None:
                raise ValueError("TPEXMarketDataAdapter requires a provider or an httpx client")
            provider = TPEXProvider(client=client)
        super().__init__(provider)


class FinMindMarketDataAdapter:
    """Adapter for Taiwan daily prices served by FinMind.

    FinMind natively supports a date range and keys on the *bare* Taiwan
    ``stock_id``, so this is the richest TW source. It claims bare TW codes
    (``"2330"``) and suffixed TW symbols alike — the registry prefers it
    for ``MarketClass.TW`` (bare codes) where the snapshot adapters abstain.
    """

    def __init__(self, provider: FinMindStockProvider | None = None) -> None:
        self._provider = provider or FinMindStockProvider()

    @property
    def market_code(self) -> str:
        return self._provider.market

    def supports(self, symbol: str) -> bool:
        return classify_symbol(symbol) in (
            MarketClass.TW,
            MarketClass.TW_TWSE,
            MarketClass.TW_TPEX,
        )

    async def get_daily_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> list[StockPriceData]:
        prices = await self._provider.fetch_daily_prices(
            to_bare_tw_code(symbol),
            start.isoformat(),
            end.isoformat(),
        )
        return _in_range(prices, start, end)

    async def get_quote(self, symbol: str) -> StockQuote | None:
        prices = await self._provider.fetch_daily_prices(
            to_bare_tw_code(symbol),
            _quote_window_start(),
            date.today().isoformat(),
        )
        latest = _latest(prices)
        return StockQuote.from_price_data(latest) if latest else None


# Conformance: every adapter must structurally satisfy the protocol. This
# tuple is referenced by the conformance test so a newly-added adapter that
# forgets a method fails the test (and mypy) immediately.
_ADAPTER_TYPES: tuple[type[MarketDataProvider], ...] = (
    YFinanceMarketDataAdapter,
    TWSEMarketDataAdapter,
    TPEXMarketDataAdapter,
    FinMindMarketDataAdapter,
)
