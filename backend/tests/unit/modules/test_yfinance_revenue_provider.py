"""Unit tests for `YFinanceRevenueProvider._fetch_sync` — exercises the
quarterly-income-statement → RevenueRecord normalization path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from app.modules.revenue.yfinance_revenue import YFinanceRevenueProvider


def _make_stmt(
    revenue_key: str = "Total Revenue",
    columns: list | None = None,
    revenue_values: list[float] | None = None,
) -> pd.DataFrame:
    if columns is None:
        columns = pd.DatetimeIndex(
            [pd.Timestamp("2026-03-31"), pd.Timestamp("2025-12-31")]
        )
    if revenue_values is None:
        revenue_values = [1_200_000.0, 1_100_000.0]
    return pd.DataFrame({c: [v] for c, v in zip(columns, revenue_values, strict=True)}, index=[revenue_key])


def test_fetch_sync_extracts_quarterly_revenue() -> None:
    """Happy path — pd.DataFrame with Total Revenue row → RevenueRecord list."""
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = _make_stmt()

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")

    assert len(result) == 2
    # Sorted DESC by period
    assert result[0].period == "2026-Q1"
    assert result[1].period == "2025-Q4"
    assert result[0].revenue == 1_200_000.0
    assert result[0].currency == "USD"
    assert result[0].symbol == "AAPL"
    assert result[0].period_type == "quarterly"


def test_fetch_sync_falls_back_to_twd_when_currency_missing() -> None:
    """Ticker without currency attr defaults to TWD."""
    ticker = MagicMock()
    ticker.info = {}  # no currency key
    ticker.quarterly_income_stmt = _make_stmt()

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("2330.TW")

    assert result[0].currency == "TWD"


def test_fetch_sync_empty_statement_returns_empty() -> None:
    """yfinance returning empty DataFrame → no records."""
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = pd.DataFrame()

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert result == []


def test_fetch_sync_none_statement_returns_empty() -> None:
    """yfinance returning None → no records."""
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = None

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert result == []


def test_fetch_sync_skips_nan_revenue_value() -> None:
    """NaN cell → row skipped."""
    import math

    cols = pd.DatetimeIndex([pd.Timestamp("2026-03-31"), pd.Timestamp("2025-12-31")])
    stmt = pd.DataFrame({cols[0]: [math.nan], cols[1]: [1_100_000.0]}, index=["Total Revenue"])
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = stmt

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert len(result) == 1
    assert result[0].period == "2025-Q4"


def test_fetch_sync_alternate_key_totalrevenue() -> None:
    """Falls back to `TotalRevenue` key when `Total Revenue` missing."""
    stmt = _make_stmt(revenue_key="TotalRevenue")
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = stmt

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert len(result) == 2


def test_fetch_sync_alternate_key_revenue() -> None:
    """Falls back to plain `Revenue` key as last resort."""
    stmt = _make_stmt(revenue_key="Revenue")
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = stmt

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert len(result) == 2


def test_fetch_sync_no_known_revenue_key_returns_empty() -> None:
    """Statement with no recognized revenue row → empty records list."""
    cols = pd.DatetimeIndex([pd.Timestamp("2026-03-31")])
    stmt = pd.DataFrame({cols[0]: [1.0]}, index=["UnknownRow"])
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = stmt

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        result = YFinanceRevenueProvider()._fetch_sync("AAPL")
    assert result == []


async def test_fetch_revenue_async_wrapper_runs_executor() -> None:
    """Async entry point should call _fetch_sync via run_in_executor."""
    ticker = MagicMock()
    ticker.info = {"currency": "USD"}
    ticker.quarterly_income_stmt = _make_stmt()

    with patch("app.modules.revenue.yfinance_revenue.yf.Ticker", return_value=ticker):
        provider = YFinanceRevenueProvider()
        result = await provider.fetch_revenue("AAPL")

    assert len(result) == 2
