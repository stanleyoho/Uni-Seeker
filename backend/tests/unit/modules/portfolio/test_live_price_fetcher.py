"""Unit tests for `app.modules.portfolio.live_price_fetcher`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §8.

Coverage (~5 cases):
  L01 fetch_quotes returns PriceQuote for a known stock_id (2 rows)
  L02 prev_close is the second-most-recent row
  L03 single-row case → prev_close == last_price (delta=0 safe)
  L04 missing stock_id → omitted from result dict (partial return)
  L05 multi-stock batch → dict keyed by stock_id

Uses an in-memory `FakeSession` mock that records the params each call
received and returns canned rows.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.modules.portfolio.live_price_fetcher import (
    DailyCloseLivePriceFetcher,
    LivePriceFetcher,
    PriceQuote,
)

# ── fakes ────────────────────────────────────────────────────────────────


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
    """Minimal Session stand-in.

    `rows_by_sid` maps `sid` query param → list of rows (already in
    DESC-by-date order, mimicking the actual SQL `ORDER BY date DESC LIMIT 2`).
    """

    def __init__(self, rows_by_sid: dict[str, list[_Row]]) -> None:
        self._rows_by_sid = rows_by_sid
        self.calls: list[str] = []

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def execute(self, _stmt, params):
        sid = params["sid"]
        self.calls.append(sid)
        return _FakeResult(self._rows_by_sid.get(sid, []))


def _factory(rows_by_sid: dict[str, list[_Row]]):
    """Return a session_factory closure compatible with the impl."""
    session = _FakeSession(rows_by_sid)

    def make():
        return session

    make.session = session  # for inspection in tests
    return make


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ── tests ────────────────────────────────────────────────────────────────


def test_L00_impl_satisfies_protocol():
    """DailyCloseLivePriceFetcher must be a LivePriceFetcher (structural)."""
    fetcher: LivePriceFetcher = DailyCloseLivePriceFetcher(_factory({}))
    # Calling fetch_quotes with empty list must return {} without DB calls.
    result = _run(fetcher.fetch_quotes([]))
    assert result == {}


# L01 — known stock_id returns PriceQuote with last_price = newest close
def test_L01_known_stock_returns_quote():
    rows = {
        "2330.TW": [
            _Row(close=Decimal("600"), date=date(2026, 5, 19)),
            _Row(close=Decimal("590"), date=date(2026, 5, 18)),
        ],
    }
    fetcher = DailyCloseLivePriceFetcher(_factory(rows))
    result = _run(fetcher.fetch_quotes(["2330.TW"]))

    assert "2330.TW" in result
    quote = result["2330.TW"]
    assert isinstance(quote, PriceQuote)
    assert quote.stock_id == "2330.TW"
    assert quote.last_price == Decimal("600")
    assert quote.prev_close == Decimal("590")
    assert quote.as_of == datetime(2026, 5, 19, tzinfo=UTC)


# L02 — prev_close is the second-most-recent (already asserted in L01;
# this is an explicit standalone case for the contract).
def test_L02_prev_close_is_second_row():
    rows = {
        "NVDA": [
            _Row(close=Decimal("1000.5"), date=date(2026, 5, 19)),
            _Row(close=Decimal("950.25"), date=date(2026, 5, 18)),
        ],
    }
    fetcher = DailyCloseLivePriceFetcher(_factory(rows))
    quote = _run(fetcher.fetch_quotes(["NVDA"]))["NVDA"]
    assert quote.last_price == Decimal("1000.5")
    assert quote.prev_close == Decimal("950.25")


# L03 — only 1 row available → prev_close = last_price (delta = 0 safe)
def test_L03_single_row_falls_back_to_last_price():
    rows = {
        "NEW.IPO": [_Row(close=Decimal("42"), date=date(2026, 5, 19))],
    }
    fetcher = DailyCloseLivePriceFetcher(_factory(rows))
    quote = _run(fetcher.fetch_quotes(["NEW.IPO"]))["NEW.IPO"]
    assert quote.last_price == Decimal("42")
    assert quote.prev_close == Decimal("42")


# L04 — stock_id with no rows is omitted from the result dict
def test_L04_missing_stock_id_omitted():
    rows = {
        "2330.TW": [
            _Row(close=Decimal("600"), date=date(2026, 5, 19)),
            _Row(close=Decimal("590"), date=date(2026, 5, 18)),
        ],
        # "GHOST" absent → no rows
    }
    fetcher = DailyCloseLivePriceFetcher(_factory(rows))
    result = _run(fetcher.fetch_quotes(["2330.TW", "GHOST"]))

    assert set(result.keys()) == {"2330.TW"}  # partial dict per contract


# L05 — multi-stock batch returns dict with all available
def test_L05_multi_stock_batch():
    rows = {
        "2330.TW": [
            _Row(close=Decimal("600"), date=date(2026, 5, 19)),
            _Row(close=Decimal("590"), date=date(2026, 5, 18)),
        ],
        "NVDA": [
            _Row(close=Decimal("1000"), date=date(2026, 5, 19)),
            _Row(close=Decimal("980"), date=date(2026, 5, 18)),
        ],
    }
    fetcher = DailyCloseLivePriceFetcher(_factory(rows))
    result = _run(fetcher.fetch_quotes(["2330.TW", "NVDA"]))

    assert set(result.keys()) == {"2330.TW", "NVDA"}
    assert result["2330.TW"].last_price == Decimal("600")
    assert result["NVDA"].last_price == Decimal("1000")
    assert result["NVDA"].prev_close == Decimal("980")
