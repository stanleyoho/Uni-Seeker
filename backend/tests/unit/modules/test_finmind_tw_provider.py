"""Unit tests for FinMindTWFinancialProvider.

Covers `_parse_statements` (pure compute) + `fetch_financials` (mocks
FinMindFundamentalProvider). No network access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.modules.financial_analysis.finmind_tw_provider import (
    _BALANCE_MAP,
    _INCOME_MAP,
    FinMindTWFinancialProvider,
)


def _row(date: str, origin_name: str, value: float) -> dict[str, object]:
    return {
        "date": date,
        "stock_id": "2330",
        "type": "X",
        "origin_name": origin_name,
        "value": value,
    }


# ── _parse_statements ────────────────────────────────────────────────────


def test_parse_statements_empty_rows_returns_empty() -> None:
    provider = FinMindTWFinancialProvider()
    assert provider._parse_statements([], _INCOME_MAP) == []


def test_parse_statements_unknown_origin_name_skipped() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [_row("2026-03-31", "不知道的欄位", 1000.0)]
    assert provider._parse_statements(rows, _INCOME_MAP) == []


def test_parse_statements_maps_origin_name_to_yfinance() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [
        _row("2026-03-31", "營業收入合計", 1_000_000),
        _row("2026-03-31", "營業毛利（毛損）", 400_000),
        _row("2026-03-31", "本期淨利（淨損）", 150_000),
    ]
    stmts = provider._parse_statements(rows, _INCOME_MAP)
    assert len(stmts) == 1
    assert stmts[0].period == "2026-03-31"
    assert stmts[0].period_type == "quarterly"
    assert stmts[0].data["Total Revenue"] == 1_000_000.0
    assert stmts[0].data["Gross Profit"] == 400_000.0
    assert stmts[0].data["Net Income"] == 150_000.0


def test_parse_statements_dedupes_first_seen_wins() -> None:
    """Two origin_names mapping to same yfinance key on the same date
    → first wins, second silently dropped."""
    provider = FinMindTWFinancialProvider()
    rows = [
        _row("2026-03-31", "營業收入合計", 1000.0),
        _row("2026-03-31", "營業收入", 2000.0),  # also Total Revenue
    ]
    stmts = provider._parse_statements(rows, _INCOME_MAP)
    assert stmts[0].data["Total Revenue"] == 1000.0


def test_parse_statements_skips_rows_missing_date() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [{"origin_name": "營業收入合計", "value": 1000.0}]  # no date
    assert provider._parse_statements(rows, _INCOME_MAP) == []


def test_parse_statements_skips_rows_with_none_value() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [{"date": "2026-03-31", "origin_name": "營業收入合計", "value": None}]
    assert provider._parse_statements(rows, _INCOME_MAP) == []


def test_parse_statements_skips_non_castable_value() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [_row("2026-03-31", "營業收入合計", "not-a-number")]  # type: ignore[arg-type]
    assert provider._parse_statements(rows, _INCOME_MAP) == []


def test_parse_statements_returns_sorted_desc() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [
        _row("2025-12-31", "營業收入合計", 1000.0),
        _row("2026-03-31", "營業收入合計", 1200.0),
        _row("2025-09-30", "營業收入合計", 900.0),
    ]
    stmts = provider._parse_statements(rows, _INCOME_MAP)
    periods = [s.period for s in stmts]
    assert periods == ["2026-03-31", "2025-12-31", "2025-09-30"]


def test_parse_statements_caps_at_20_periods() -> None:
    """sorted_dates[:20] cap — 25 periods → only top 20 returned."""
    provider = FinMindTWFinancialProvider()
    rows = [_row(f"{2010 + i}-03-31", "營業收入合計", 1000.0 + i) for i in range(25)]
    stmts = provider._parse_statements(rows, _INCOME_MAP)
    assert len(stmts) == 20


def test_parse_balance_sheet_map_picks_correct_yfinance_names() -> None:
    provider = FinMindTWFinancialProvider()
    rows = [
        _row("2026-03-31", "資產總計", 5_000_000),
        _row("2026-03-31", "現金及約當現金", 800_000),
    ]
    stmts = provider._parse_statements(rows, _BALANCE_MAP)
    assert stmts[0].data["Total Assets"] == 5_000_000.0
    assert stmts[0].data["Cash And Cash Equivalents"] == 800_000.0


# ── fetch_financials ──────────────────────────────────────────────────────


async def test_fetch_financials_assembles_three_statements() -> None:
    """fetch_financials runs three concurrent provider calls + assembles
    FinancialData (TWD currency)."""
    mock_provider = MagicMock()
    mock_provider.fetch_income_statement = AsyncMock(
        return_value=[_row("2026-03-31", "營業收入合計", 1_000_000)]
    )
    mock_provider.fetch_balance_sheet = AsyncMock(
        return_value=[_row("2026-03-31", "資產總計", 5_000_000)]
    )
    mock_provider.fetch_cash_flow = AsyncMock(return_value=[])

    provider = FinMindTWFinancialProvider()
    provider._provider = mock_provider

    data = await provider.fetch_financials("2330")
    assert data.symbol == "2330"
    assert data.currency == "TWD"
    assert len(data.income_statements) == 1
    assert len(data.balance_sheets) == 1
    assert data.cash_flows == []

    mock_provider.fetch_income_statement.assert_awaited_once()
    mock_provider.fetch_balance_sheet.assert_awaited_once()
    mock_provider.fetch_cash_flow.assert_awaited_once()


async def test_fetch_financials_empty_provider_returns_empty_statements() -> None:
    mock_provider = MagicMock()
    mock_provider.fetch_income_statement = AsyncMock(return_value=[])
    mock_provider.fetch_balance_sheet = AsyncMock(return_value=[])
    mock_provider.fetch_cash_flow = AsyncMock(return_value=[])

    provider = FinMindTWFinancialProvider()
    provider._provider = mock_provider

    data = await provider.fetch_financials("9999")
    assert data.income_statements == []
    assert data.balance_sheets == []
    assert data.cash_flows == []
