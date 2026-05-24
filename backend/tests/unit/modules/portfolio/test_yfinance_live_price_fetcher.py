"""Unit tests for `YFinanceLivePriceFetcher`, `TTLCacheMixin`, and
`CachedDailyCloseLivePriceFetcher`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §8.4 / §13.

Test groups (~12 cases):
  Y01–Y04  YFinance fetcher (monkey-patched yfinance module)
  T01–T04  TTL cache (monkey-patched monotonic clock)
  C01–C02  CachedDailyCloseLivePriceFetcher wrapper

Mocking strategy:
  - yfinance: we install a minimal fake `yfinance` module into `sys.modules`.
    The fetcher imports it lazily inside `_fetch_one_sync` so the substitution
    is honoured per test.
  - clock: we replace `_now` on the instance with a deterministic counter to
    avoid `time.sleep` (which slows the suite and is flake-prone).
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.modules.portfolio.live_price_fetcher import (
    CachedDailyCloseLivePriceFetcher,
    CompositeLivePriceFetcher,
    DailyCloseLivePriceFetcher,
    PriceQuote,
    TTLCacheMixin,
    YFinanceLivePriceFetcher,
)

# ── helpers ──────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


@dataclass
class _FakeIndex:
    """Mimic pandas Timestamp `.year`/`.month`/`.day` + `to_pydatetime()`."""

    dt: datetime

    @property
    def year(self) -> int:
        return self.dt.year

    @property
    def month(self) -> int:
        return self.dt.month

    @property
    def day(self) -> int:
        return self.dt.day

    def to_pydatetime(self) -> datetime:
        return self.dt


class _FakeSeries:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeDataFrame:
    """Tiny stand-in for the slice of pandas we touch (`["Close"]`, `.index`,
    `.empty`)."""

    def __init__(self, closes: list[float], dates: list[datetime]) -> None:
        self._closes = list(closes)
        self.index = [_FakeIndex(d) for d in dates]
        self.empty = len(closes) == 0

    def __getitem__(self, key: str) -> _FakeSeries:
        if key == "Close":
            return _FakeSeries(self._closes)
        raise KeyError(key)


class _FakeTicker:
    def __init__(self, frames: dict[str, _FakeDataFrame], symbol: str,
                 raise_on: set[str]) -> None:
        self._frames = frames
        self._symbol = symbol
        self._raise_on = raise_on

    def history(self, period: str = "2d", interval: str = "1d") -> _FakeDataFrame:
        if self._symbol in self._raise_on:
            raise RuntimeError(f"simulated network error for {self._symbol}")
        return self._frames.get(self._symbol, _FakeDataFrame([], []))


def _install_fake_yfinance(
    monkeypatch: pytest.MonkeyPatch,
    frames: dict[str, _FakeDataFrame],
    raise_on: set[str] | None = None,
) -> dict[str, int]:
    """Install a fake `yfinance` module; return a call-count dict."""
    raise_on = raise_on or set()
    call_count: dict[str, int] = {}

    class _FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> _FakeTicker:
            call_count[symbol] = call_count.get(symbol, 0) + 1
            return _FakeTicker(frames, symbol, raise_on)

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF())
    return call_count


# ── Y: YFinanceLivePriceFetcher ─────────────────────────────────────────


def test_Y01_returns_quote_for_known_symbol(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "NVDA": _FakeDataFrame(
            closes=[950.25, 1000.5],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    result = _run(fetcher.fetch_quotes(["NVDA"]))

    assert "NVDA" in result
    quote = result["NVDA"]
    assert isinstance(quote, PriceQuote)
    assert quote.stock_id == "NVDA"
    assert quote.last_price == Decimal("1000.5")
    assert quote.prev_close == Decimal("950.25")
    assert quote.as_of == datetime(2026, 5, 19)


def test_Y02_batches_multiple_symbols(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "2330.TW": _FakeDataFrame(
            closes=[590.0, 600.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
        "NVDA": _FakeDataFrame(
            closes=[980.0, 1000.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    calls = _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    result = _run(fetcher.fetch_quotes(["2330.TW", "NVDA"]))

    assert set(result.keys()) == {"2330.TW", "NVDA"}
    assert result["2330.TW"].last_price == Decimal("600.0")
    assert result["NVDA"].prev_close == Decimal("980.0")
    # Single-symbol per call → exactly one Ticker(...) call each.
    assert calls["2330.TW"] == 1
    assert calls["NVDA"] == 1


def test_Y03_handles_missing_symbol(monkeypatch: pytest.MonkeyPatch):
    # GHOST returns an empty DataFrame → omitted from result.
    frames = {
        "NVDA": _FakeDataFrame(
            closes=[980.0, 1000.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
        "GHOST": _FakeDataFrame(closes=[], dates=[]),
    }
    _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    result = _run(fetcher.fetch_quotes(["NVDA", "GHOST"]))

    assert set(result.keys()) == {"NVDA"}


def test_Y04_network_error_logs_and_omits(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "NVDA": _FakeDataFrame(
            closes=[980.0, 1000.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
        "FLAKY": _FakeDataFrame(  # data is fine but Ticker(...) raises
            closes=[10.0, 11.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yfinance(monkeypatch, frames, raise_on={"FLAKY"})

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    # Must not raise — failed symbol is gracefully omitted.
    result = _run(fetcher.fetch_quotes(["NVDA", "FLAKY"]))
    assert set(result.keys()) == {"NVDA"}


def test_Y05_single_row_history_uses_last_as_prev(monkeypatch: pytest.MonkeyPatch):
    # Newly listed symbol with only one daily bar — prev_close == last_price.
    frames = {
        "IPO.NEW": _FakeDataFrame(
            closes=[42.0],
            dates=[datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yfinance(monkeypatch, frames)
    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    result = _run(fetcher.fetch_quotes(["IPO.NEW"]))
    q = result["IPO.NEW"]
    assert q.last_price == Decimal("42.0")
    assert q.prev_close == Decimal("42.0")


# ── T: TTL cache ────────────────────────────────────────────────────────


def _stub_clock(fetcher: TTLCacheMixin, holder: dict[str, float]) -> None:
    """Replace `_now` with a settable counter held in `holder['t']`."""
    fetcher._now = lambda: holder["t"]  # type: ignore[method-assign]


def test_T01_cache_hit_skips_refetch(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "NVDA": _FakeDataFrame(
            closes=[980.0, 1000.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    calls = _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    clock = {"t": 0.0}
    _stub_clock(fetcher, clock)

    _run(fetcher.fetch_quotes(["NVDA"]))
    clock["t"] = 30.0  # within TTL
    _run(fetcher.fetch_quotes(["NVDA"]))

    # Only the first call went out to the network.
    assert calls["NVDA"] == 1


def test_T02_cache_miss_after_expiry(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "NVDA": _FakeDataFrame(
            closes=[980.0, 1000.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    calls = _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    clock = {"t": 0.0}
    _stub_clock(fetcher, clock)

    _run(fetcher.fetch_quotes(["NVDA"]))
    clock["t"] = 120.0  # past TTL (60s)
    _run(fetcher.fetch_quotes(["NVDA"]))
    assert calls["NVDA"] == 2


def test_T03_per_symbol_expiration(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "AAA": _FakeDataFrame(
            closes=[10.0, 11.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
        "BBB": _FakeDataFrame(
            closes=[20.0, 21.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    calls = _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    clock = {"t": 0.0}
    _stub_clock(fetcher, clock)

    # Cache AAA at t=0; cache BBB at t=50.
    _run(fetcher.fetch_quotes(["AAA"]))
    clock["t"] = 50.0
    _run(fetcher.fetch_quotes(["BBB"]))

    # At t=70: AAA expired (70 > 0+60), BBB still fresh (70 < 50+60).
    clock["t"] = 70.0
    _run(fetcher.fetch_quotes(["AAA", "BBB"]))

    assert calls["AAA"] == 2  # re-fetched
    assert calls["BBB"] == 1  # served from cache


def test_T04_purge_expired_drops_stale_entries(monkeypatch: pytest.MonkeyPatch):
    frames = {
        "AAA": _FakeDataFrame(
            closes=[10.0, 11.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
        "BBB": _FakeDataFrame(
            closes=[20.0, 21.0],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yfinance(monkeypatch, frames)

    fetcher = YFinanceLivePriceFetcher(ttl_seconds=60)
    clock = {"t": 0.0}
    _stub_clock(fetcher, clock)

    _run(fetcher.fetch_quotes(["AAA", "BBB"]))
    assert len(fetcher._cache) == 2

    clock["t"] = 9999.0  # everything expired
    purged = fetcher._purge_expired()
    assert purged == 2
    assert fetcher._cache == {}


def test_T05_ttl_must_be_positive():
    with pytest.raises(ValueError):
        YFinanceLivePriceFetcher(ttl_seconds=0)


# ── C: CachedDailyCloseLivePriceFetcher ─────────────────────────────────


@dataclass
class _Row:
    close: Decimal
    date: date


class _FakeResult:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def all(self) -> list[_Row]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows_by_sid: dict[str, list[_Row]]) -> None:
        self._rows_by_sid = rows_by_sid
        self.calls: list[str] = []

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def execute(self, _stmt: Any, params: dict[str, Any]) -> _FakeResult:
        sid = params["sid"]
        self.calls.append(sid)
        return _FakeResult(self._rows_by_sid.get(sid, []))


def _factory(rows_by_sid: dict[str, list[_Row]]):
    session = _FakeSession(rows_by_sid)

    def make():
        return session

    make.session = session  # type: ignore[attr-defined]
    return make


def test_C01_falls_through_to_inner_on_miss():
    rows = {
        "NVDA": [
            _Row(close=Decimal("1000"), date=date(2026, 5, 19)),
            _Row(close=Decimal("980"), date=date(2026, 5, 18)),
        ],
    }
    factory = _factory(rows)
    fetcher = CachedDailyCloseLivePriceFetcher(factory, ttl_seconds=300)
    result = _run(fetcher.fetch_quotes(["NVDA"]))

    assert result["NVDA"].last_price == Decimal("1000")
    assert factory.session.calls == ["NVDA"]


def test_C02_serves_subsequent_calls_from_cache():
    rows = {
        "NVDA": [
            _Row(close=Decimal("1000"), date=date(2026, 5, 19)),
            _Row(close=Decimal("980"), date=date(2026, 5, 18)),
        ],
    }
    factory = _factory(rows)
    fetcher = CachedDailyCloseLivePriceFetcher(factory, ttl_seconds=300)
    clock = {"t": 0.0}
    _stub_clock(fetcher, clock)

    _run(fetcher.fetch_quotes(["NVDA"]))
    clock["t"] = 100.0  # well within TTL
    _run(fetcher.fetch_quotes(["NVDA"]))

    # The inner DB layer is only consulted on the first call.
    assert factory.session.calls == ["NVDA"]


# ── X: CompositeLivePriceFetcher ────────────────────────────────────────


class _StubFetcher:
    """Deterministic `LivePriceFetcher` test double — returns the quotes
    provided for whichever requested symbols match.

    Set `raise_on_call=True` to simulate total upstream failure (e.g.
    yfinance throwing during the network round-trip).
    """

    def __init__(
        self,
        quotes: dict[str, PriceQuote] | None = None,
        *,
        raise_on_call: bool = False,
    ) -> None:
        self._quotes = quotes or {}
        self._raise = raise_on_call
        self.received_symbols: list[list[str]] = []

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
        self.received_symbols.append(list(stock_ids))
        if self._raise:
            raise RuntimeError("simulated upstream outage")
        return {sid: self._quotes[sid] for sid in stock_ids if sid in self._quotes}


def _quote(sym: str, last: str, prev: str) -> PriceQuote:
    return PriceQuote(
        stock_id=sym,
        last_price=Decimal(last),
        prev_close=Decimal(prev),
        as_of=datetime(2026, 5, 19),
    )


def test_X01_composite_returns_primary_results_when_all_present():
    primary = _StubFetcher({
        "NVDA": _quote("NVDA", "1000", "980"),
        "AAPL": _quote("AAPL", "200", "198"),
    })
    secondary = _StubFetcher({
        "NVDA": _quote("NVDA", "999", "888"),  # should be ignored
    })
    composite = CompositeLivePriceFetcher(primary, secondary)

    result = _run(composite.fetch_quotes(["NVDA", "AAPL"]))

    assert set(result.keys()) == {"NVDA", "AAPL"}
    assert result["NVDA"].last_price == Decimal("1000")
    # Secondary must not be consulted when primary covers everything.
    assert secondary.received_symbols == []


def test_X02_composite_falls_back_for_missing_symbols():
    # Primary covers NVDA only; secondary covers GHOST.
    primary = _StubFetcher({"NVDA": _quote("NVDA", "1000", "980")})
    secondary = _StubFetcher({
        "GHOST": _quote("GHOST", "5", "4"),
    })
    composite = CompositeLivePriceFetcher(primary, secondary)

    result = _run(composite.fetch_quotes(["NVDA", "GHOST"]))

    assert set(result.keys()) == {"NVDA", "GHOST"}
    assert result["NVDA"].last_price == Decimal("1000")
    assert result["GHOST"].last_price == Decimal("5")
    # Secondary should only have been asked about the gap.
    assert secondary.received_symbols == [["GHOST"]]


def test_X03_composite_falls_back_for_all_missing():
    # Primary's network is dead → all symbols routed to secondary.
    primary = _StubFetcher(raise_on_call=True)
    secondary = _StubFetcher({
        "NVDA": _quote("NVDA", "1000", "980"),
        "AAPL": _quote("AAPL", "200", "198"),
    })
    composite = CompositeLivePriceFetcher(primary, secondary)

    result = _run(composite.fetch_quotes(["NVDA", "AAPL"]))

    assert set(result.keys()) == {"NVDA", "AAPL"}
    assert secondary.received_symbols == [["NVDA", "AAPL"]]


def test_X04_composite_partial_result_when_secondary_also_misses():
    # Primary covers AAPL; secondary doesn't know GHOST either.
    primary = _StubFetcher({"AAPL": _quote("AAPL", "200", "198")})
    secondary = _StubFetcher({})  # empty
    composite = CompositeLivePriceFetcher(primary, secondary)

    result = _run(composite.fetch_quotes(["AAPL", "GHOST"]))

    # Partial dict — GHOST gracefully omitted, contract per spec §12 R8.
    assert set(result.keys()) == {"AAPL"}
    assert secondary.received_symbols == [["GHOST"]]


def test_X05_composite_primary_wins_on_overlap():
    # Defensive: even if secondary somehow returns a symbol the primary
    # already covered, the primary's quote must be preserved.
    primary = _StubFetcher({"NVDA": _quote("NVDA", "1000", "980")})

    class _PromiscuousSecondary:
        async def fetch_quotes(
            self, stock_ids: list[str]
        ) -> dict[str, PriceQuote]:
            # Ignores the requested list — returns its own NVDA anyway.
            return {"NVDA": _quote("NVDA", "1", "1")}

    composite = CompositeLivePriceFetcher(primary, _PromiscuousSecondary())

    result = _run(composite.fetch_quotes(["NVDA"]))

    # Primary's value wins.
    assert result["NVDA"].last_price == Decimal("1000")


def test_X06_composite_logs_warning_when_fallback_engages(capsys):
    primary = _StubFetcher({"NVDA": _quote("NVDA", "1000", "980")})
    secondary = _StubFetcher({"GHOST": _quote("GHOST", "5", "4")})
    composite = CompositeLivePriceFetcher(primary, secondary)

    _run(composite.fetch_quotes(["NVDA", "GHOST"]))

    # `structlog.get_logger()` in this project renders to stdout by default,
    # so we capture there (caplog only sees stdlib logging records). What
    # matters is that the named event reached the ops stream tagged with
    # the missing symbols, regardless of which formatter ultimately receives it.
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "composite_fallback_engaged" in combined
    assert "GHOST" in combined


def test_X07_composite_empty_input_short_circuits():
    primary = _StubFetcher({"NVDA": _quote("NVDA", "1000", "980")})
    secondary = _StubFetcher({"GHOST": _quote("GHOST", "5", "4")})
    composite = CompositeLivePriceFetcher(primary, secondary)

    result = _run(composite.fetch_quotes([]))

    assert result == {}
    # Neither fetcher should be invoked.
    assert primary.received_symbols == []
    assert secondary.received_symbols == []
