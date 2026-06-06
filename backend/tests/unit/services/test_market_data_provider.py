"""Tests for the unified MarketDataProvider abstraction (A2 audit item)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.modules.price_updater.base import StockPriceData
from app.services.market_data import (
    MarketClass,
    MarketDataProvider,
    MarketDataRegistry,
    NoProviderError,
    StockQuote,
    build_default_registry,
    classify_symbol,
    to_bare_tw_code,
)
from app.services.market_data.adapters import (
    _ADAPTER_TYPES,
    FinMindMarketDataAdapter,
    TPEXMarketDataAdapter,
    TWSEMarketDataAdapter,
    YFinanceMarketDataAdapter,
)

# ---------------------------------------------------------------------------
# Symbol classification (the routing primitive)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("2330.TW", MarketClass.TW_TWSE),
        ("2330.tw", MarketClass.TW_TWSE),
        ("6488.TWO", MarketClass.TW_TPEX),
        ("6488.two", MarketClass.TW_TPEX),
        ("2330", MarketClass.TW),
        ("00830", MarketClass.TW),
        ("AAPL", MarketClass.US),
        ("BRK.B", MarketClass.US),
        ("  TSLA  ", MarketClass.US),
    ],
)
def test_classify_symbol(symbol: str, expected: MarketClass) -> None:
    assert classify_symbol(symbol) is expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("2330.TW", "2330"),
        ("6488.TWO", "6488"),
        ("2330", "2330"),
        ("AAPL", "AAPL"),
    ],
)
def test_to_bare_tw_code(symbol: str, expected: str) -> None:
    assert to_bare_tw_code(symbol) == expected


# ---------------------------------------------------------------------------
# Conformance: every adapter structurally satisfies the protocol
# ---------------------------------------------------------------------------


def test_all_adapters_conform_to_protocol() -> None:
    client = AsyncMock()
    instances: list[MarketDataProvider] = [
        YFinanceMarketDataAdapter(),
        TWSEMarketDataAdapter(client=client),
        TPEXMarketDataAdapter(client=client),
        FinMindMarketDataAdapter(),
    ]
    for inst in instances:
        assert isinstance(inst, MarketDataProvider), type(inst).__name__


def test_adapter_types_registry_lists_every_adapter() -> None:
    # The conformance tuple in adapters.py must stay in sync with the
    # actual adapter classes so a newly-added adapter cannot silently
    # escape conformance checks.
    assert set(_ADAPTER_TYPES) == {
        YFinanceMarketDataAdapter,
        TWSEMarketDataAdapter,
        TPEXMarketDataAdapter,
        FinMindMarketDataAdapter,
    }


# ---------------------------------------------------------------------------
# Capability discrimination (supports)
# ---------------------------------------------------------------------------


def test_yfinance_supports_only_us() -> None:
    a = YFinanceMarketDataAdapter()
    assert a.supports("AAPL") is True
    assert a.supports("2330.TW") is False
    assert a.supports("6488.TWO") is False
    assert a.supports("2330") is False


def test_twse_supports_only_tw_suffix() -> None:
    a = TWSEMarketDataAdapter(client=AsyncMock())
    assert a.supports("2330.TW") is True
    assert a.supports("6488.TWO") is False
    assert a.supports("2330") is False  # bare code abstained
    assert a.supports("AAPL") is False


def test_tpex_supports_only_two_suffix() -> None:
    a = TPEXMarketDataAdapter(client=AsyncMock())
    assert a.supports("6488.TWO") is True
    assert a.supports("2330.TW") is False
    assert a.supports("AAPL") is False


def test_finmind_supports_all_tw() -> None:
    a = FinMindMarketDataAdapter()
    assert a.supports("2330") is True
    assert a.supports("2330.TW") is True
    assert a.supports("6488.TWO") is True
    assert a.supports("AAPL") is False


def test_adapter_market_codes() -> None:
    assert YFinanceMarketDataAdapter().market_code == "US_NASDAQ"
    assert TWSEMarketDataAdapter(client=AsyncMock()).market_code == "TW_TWSE"
    assert TPEXMarketDataAdapter(client=AsyncMock()).market_code == "TW_TPEX"
    assert FinMindMarketDataAdapter().market_code == "TW_TWSE"


# ---------------------------------------------------------------------------
# Registry resolution: TW vs US routes to the right provider
# ---------------------------------------------------------------------------


def test_registry_routes_us_symbol_to_yfinance() -> None:
    reg = build_default_registry(client=AsyncMock())
    provider = reg.for_symbol("AAPL")
    assert isinstance(provider, YFinanceMarketDataAdapter)


def test_registry_routes_twse_symbol_to_twse_adapter() -> None:
    reg = build_default_registry(client=AsyncMock())
    provider = reg.for_symbol("2330.TW")
    # TWSE snapshot adapter is registered before FinMind -> first match.
    assert isinstance(provider, TWSEMarketDataAdapter)


def test_registry_routes_tpex_symbol_to_tpex_adapter() -> None:
    reg = build_default_registry(client=AsyncMock())
    provider = reg.for_symbol("6488.TWO")
    assert isinstance(provider, TPEXMarketDataAdapter)


def test_registry_routes_bare_tw_code_to_finmind() -> None:
    # A bare TW code (no board suffix) is abstained by the snapshot
    # adapters and falls through to FinMind.
    reg = build_default_registry(client=AsyncMock())
    provider = reg.for_symbol("2330")
    assert isinstance(provider, FinMindMarketDataAdapter)


def test_registry_without_client_skips_snapshot_adapters() -> None:
    reg = build_default_registry(client=None)
    # No TWSE/TPEX snapshot adapters -> suffixed TW symbol routes to FinMind.
    assert isinstance(reg.for_symbol("2330.TW"), FinMindMarketDataAdapter)
    assert isinstance(reg.for_symbol("AAPL"), YFinanceMarketDataAdapter)


def test_registry_raises_when_no_provider() -> None:
    reg = MarketDataRegistry([YFinanceMarketDataAdapter()])
    # yfinance only supports US; a TW symbol has no provider here.
    assert reg.resolve("2330.TW") is None
    with pytest.raises(NoProviderError) as exc:
        reg.for_symbol("2330.TW")
    assert exc.value.symbol == "2330.TW"


def test_registry_register_appends_in_order() -> None:
    reg = MarketDataRegistry()
    fin = FinMindMarketDataAdapter()
    yf = YFinanceMarketDataAdapter()
    reg.register(fin)
    reg.register(yf)
    assert reg.providers == [fin, yf]


# ---------------------------------------------------------------------------
# Uniform surface delegates correctly (no network — adapters wrap mocks)
# ---------------------------------------------------------------------------


def _sample_bar(d: date, close: str) -> StockPriceData:
    return StockPriceData(
        symbol="2330.TW",
        market="TW_TWSE",
        date=d,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal(close),
        volume=1000,
    )


async def test_finmind_adapter_get_daily_ohlcv_filters_range() -> None:
    underlying = AsyncMock()
    underlying.fetch_daily_prices.return_value = [
        _sample_bar(date(2026, 1, 1), "100"),
        _sample_bar(date(2026, 1, 5), "105"),
        _sample_bar(date(2026, 2, 1), "110"),  # outside range
    ]
    adapter = FinMindMarketDataAdapter(provider=underlying)
    bars = await adapter.get_daily_ohlcv("2330.TW", date(2026, 1, 1), date(2026, 1, 31))

    assert [b.date for b in bars] == [date(2026, 1, 1), date(2026, 1, 5)]
    # bare stock_id is passed to the underlying FinMind provider
    call_args = underlying.fetch_daily_prices.call_args
    assert call_args.args[0] == "2330"


async def test_finmind_adapter_get_quote_returns_latest() -> None:
    underlying = AsyncMock()
    underlying.fetch_daily_prices.return_value = [
        _sample_bar(date(2026, 1, 1), "100"),
        _sample_bar(date(2026, 1, 5), "105"),
    ]
    adapter = FinMindMarketDataAdapter(provider=underlying)
    quote = await adapter.get_quote("2330.TW")

    assert isinstance(quote, StockQuote)
    assert quote.date == date(2026, 1, 5)
    assert quote.close == Decimal("105")


async def test_finmind_adapter_get_quote_none_when_empty() -> None:
    underlying = AsyncMock()
    underlying.fetch_daily_prices.return_value = []
    adapter = FinMindMarketDataAdapter(provider=underlying)
    assert await adapter.get_quote("2330.TW") is None


async def test_twse_adapter_strips_suffix_for_underlying() -> None:
    underlying = AsyncMock()
    underlying.market = "TW_TWSE"
    underlying.fetch_daily_prices.return_value = [_sample_bar(date(2026, 1, 5), "105")]
    adapter = TWSEMarketDataAdapter(provider=underlying)

    quote = await adapter.get_quote("2330.TW")
    assert quote is not None
    assert quote.close == Decimal("105")
    # snapshot provider filters on bare code
    assert underlying.fetch_daily_prices.call_args.args[0] == "2330"


async def test_yfinance_adapter_get_quote_delegates() -> None:
    underlying = AsyncMock()
    underlying.market = "US_NASDAQ"
    underlying.fetch_daily_prices.return_value = [
        StockPriceData(
            symbol="AAPL",
            market="US_NASDAQ",
            date=date(2026, 1, 5),
            open=Decimal("180"),
            high=Decimal("185"),
            low=Decimal("179"),
            close=Decimal("184"),
            volume=5000,
        )
    ]
    adapter = YFinanceMarketDataAdapter(provider=underlying)
    quote = await adapter.get_quote("AAPL")
    assert quote is not None
    assert quote.symbol == "AAPL"
    assert quote.close == Decimal("184")


def test_yfinance_period_for_span() -> None:
    f = YFinanceMarketDataAdapter._period_for_span
    assert f(3) == "5d"
    assert f(20) == "1mo"
    assert f(60) == "3mo"
    assert f(150) == "6mo"
    assert f(300) == "1y"
    assert f(700) == "2y"
    assert f(1500) == "5y"
    assert f(5000) == "max"


def test_adapter_requires_provider_or_client() -> None:
    with pytest.raises(ValueError, match="requires a provider or an httpx client"):
        TWSEMarketDataAdapter()
    with pytest.raises(ValueError, match="requires a provider or an httpx client"):
        TPEXMarketDataAdapter()
