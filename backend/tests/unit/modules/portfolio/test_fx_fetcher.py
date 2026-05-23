"""Unit tests for `YFinanceFxFetcher` — mocks yfinance via sys.modules.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11.

Pattern mirrors `test_yfinance_live_price_fetcher.py`: we install a tiny
fake `yfinance` module into `sys.modules` so the lazy import inside
`_fetch_one_sync` is rerouted per-test.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import pytest

from app.modules.portfolio.fx_fetcher import (
    FxFetchError,
    YFinanceFxFetcher,
)


# ── helpers ──────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


@dataclass
class _FakeIdx:
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


class _FakeDF:
    def __init__(self, closes: list[float], dates: list[datetime]) -> None:
        self._closes = list(closes)
        self.index = [_FakeIdx(d) for d in dates]
        self.empty = len(closes) == 0

    def __getitem__(self, key: str) -> _FakeSeries:
        if key == "Close":
            return _FakeSeries(self._closes)
        raise KeyError(key)


class _FakeTicker:
    def __init__(
        self,
        frames: dict[str, _FakeDF],
        symbol: str,
        raise_on: set[str],
    ) -> None:
        self._frames = frames
        self._symbol = symbol
        self._raise_on = raise_on

    def history(self, **_kwargs) -> _FakeDF:
        if self._symbol in self._raise_on:
            raise RuntimeError(f"sim network error: {self._symbol}")
        return self._frames.get(self._symbol, _FakeDF([], []))


def _install_fake_yf(
    monkeypatch: pytest.MonkeyPatch,
    frames: dict[str, _FakeDF],
    raise_on: set[str] | None = None,
) -> dict[str, int]:
    raise_on = raise_on or set()
    calls: dict[str, int] = {}

    class _FakeYF:
        @staticmethod
        def Ticker(symbol: str) -> _FakeTicker:  # noqa: N802
            calls[symbol] = calls.get(symbol, 0) + 1
            return _FakeTicker(frames, symbol, raise_on)

    monkeypatch.setitem(sys.modules, "yfinance", _FakeYF())
    return calls


# ── tests ────────────────────────────────────────────────────────────────


def test_F01_same_currency_returns_one(monkeypatch: pytest.MonkeyPatch):
    """`base == quote` short-circuits to Decimal('1') without API call."""
    calls = _install_fake_yf(monkeypatch, frames={})
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    rate = _run(fetcher.fetch_rate("USD", "USD"))
    assert rate == Decimal("1")
    assert calls == {}  # No API call at all.


def test_F02_direct_pair_returns_close(monkeypatch: pytest.MonkeyPatch):
    """USDJPY=X close=150.5 → fetch_rate('USD','JPY') == Decimal('150.5')."""
    frames = {
        "USDJPY=X": _FakeDF(
            closes=[149.0, 150.5],
            dates=[datetime(2026, 5, 18), datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yf(monkeypatch, frames)
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    rate = _run(fetcher.fetch_rate("USD", "JPY"))
    assert rate == Decimal("150.5")


def test_F03_cache_hit_no_second_api_call(monkeypatch: pytest.MonkeyPatch):
    """Second call within TTL returns cache without hitting yfinance again."""
    frames = {
        "USDJPY=X": _FakeDF(
            closes=[150.0],
            dates=[datetime(2026, 5, 19)],
        ),
    }
    calls = _install_fake_yf(monkeypatch, frames)
    fetcher = YFinanceFxFetcher(ttl_seconds=3600)

    _run(fetcher.fetch_rate("USD", "JPY"))
    _run(fetcher.fetch_rate("USD", "JPY"))
    _run(fetcher.fetch_rate("USD", "JPY"))

    assert calls.get("USDJPY=X") == 1


def test_F04_inverse_fallback(monkeypatch: pytest.MonkeyPatch):
    """Direct pair empty → tries inverse and returns reciprocal."""
    frames = {
        # USDJPY=X is empty.
        "USDJPY=X": _FakeDF([], []),
        # But JPYUSD=X has data: 1 JPY = 0.005 USD → reciprocal = 200.
        "JPYUSD=X": _FakeDF(
            closes=[0.005],
            dates=[datetime(2026, 5, 19)],
        ),
    }
    _install_fake_yf(monkeypatch, frames)
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    rate = _run(fetcher.fetch_rate("USD", "JPY"))
    assert rate == Decimal("200")


def test_F05_both_directions_fail_raises(monkeypatch: pytest.MonkeyPatch):
    """Direct and inverse both empty → FxFetchError."""
    frames = {
        "EURGBP=X": _FakeDF([], []),
        "GBPEUR=X": _FakeDF([], []),
    }
    _install_fake_yf(monkeypatch, frames)
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    with pytest.raises(FxFetchError):
        _run(fetcher.fetch_rate("EUR", "GBP"))


def test_F06_batch_skips_failures(monkeypatch: pytest.MonkeyPatch):
    """`fetch_rates_batch` returns successes only; failures omitted."""
    frames = {
        "USDTWD=X": _FakeDF(
            closes=[31.0],
            dates=[datetime(2026, 5, 19)],
        ),
        # JPYTWD missing in both directions.
        "JPYTWD=X": _FakeDF([], []),
        "TWDJPY=X": _FakeDF([], []),
    }
    _install_fake_yf(monkeypatch, frames)
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    out = _run(
        fetcher.fetch_rates_batch([("USD", "TWD"), ("JPY", "TWD")])
    )
    assert ("USD", "TWD") in out
    assert out[("USD", "TWD")] == Decimal("31")
    assert ("JPY", "TWD") not in out  # Failure omitted.


def test_F07_network_error_treated_as_miss(monkeypatch: pytest.MonkeyPatch):
    """Ticker(...) raising is logged + treated like empty; inverse attempted."""
    frames = {
        # Direct pair raises; inverse succeeds.
        "USDTWD=X": _FakeDF(
            closes=[31.0], dates=[datetime(2026, 5, 19)]
        ),  # not raised — see raise_on below
        "TWDUSD=X": _FakeDF(
            closes=[0.032], dates=[datetime(2026, 5, 19)]
        ),
    }
    _install_fake_yf(monkeypatch, frames, raise_on={"USDTWD=X"})
    fetcher = YFinanceFxFetcher(ttl_seconds=60)
    rate = _run(fetcher.fetch_rate("USD", "TWD"))
    # Inverse 0.032 → 1/0.032 ≈ 31.25
    assert rate == Decimal("1") / Decimal("0.032")
