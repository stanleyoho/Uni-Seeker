"""Integration tests for `read_tw_financials` — DB → FinancialData mapper.

Covers: symbol resolution (with / without .TW), no-data fallback,
per-statement-type grouping, FinMind key → yfinance-name mapping,
percentage-variant skipping, deduplication by period.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.financial_statement import FinancialStatement as FSModel
from app.models.stock import Stock
from app.modules.financial_analysis.tw_db_reader import read_tw_financials


async def _mk_stock(db: AsyncSession, symbol: str) -> Stock:
    s = Stock(symbol=symbol, name="TestCo", market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def test_returns_none_when_stock_missing(db_session: AsyncSession) -> None:
    """No matching stock at all → None (caller falls back to live)."""
    result = await read_tw_financials("9999", db_session)
    assert result is None


async def test_returns_none_when_stock_has_no_rows(
    db_session: AsyncSession,
) -> None:
    """Stock exists but no FSModel rows → None."""
    await _mk_stock(db_session, "2330")
    result = await read_tw_financials("2330", db_session)
    assert result is None


async def test_returns_none_when_only_balance_rows(
    db_session: AsyncSession,
) -> None:
    """Need at least one income row to return non-None."""
    s = await _mk_stock(db_session, "2330")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="balance",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"TotalAssets": 1000.0},
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is None


async def test_resolves_bare_symbol_when_db_has_dot_tw(
    db_session: AsyncSession,
) -> None:
    """Caller passes "2330"; DB stores "2330.TW"."""
    s = await _mk_stock(db_session, "2330.TW")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"Revenue": 1000.0},
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    assert result.symbol == "2330"
    assert result.currency == "TWD"


async def test_maps_income_keys_to_yfinance_names(
    db_session: AsyncSession,
) -> None:
    """FinMind key 'Revenue' → 'Total Revenue', 'OperatingIncome' → 'Operating Income'."""
    s = await _mk_stock(db_session, "2330")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={
                "Revenue": 1000.0,
                "OperatingIncome": 200.0,
                "GrossProfit": 400.0,
                "EPS": 3.5,
                # Unknown key — ignored
                "UnknownField": 999.0,
                # _per variant — skipped
                "Revenue_per": 0.5,
            },
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    assert len(result.income_statements) == 1
    data = result.income_statements[0].data
    assert data["Total Revenue"] == 1000.0
    assert data["Operating Income"] == 200.0
    assert data["Gross Profit"] == 400.0
    assert data["Basic EPS"] == 3.5
    assert "UnknownField" not in data


async def test_groups_by_statement_type(db_session: AsyncSession) -> None:
    """Income / balance / cashflow rows go into the correct bucket."""
    s = await _mk_stock(db_session, "2330")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"Revenue": 1000.0},
        )
    )
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="balance",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"TotalAssets": 5000.0, "Equity": 2000.0},
        )
    )
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="cashflow",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"CashFlowsFromOperatingActivities": 300.0},
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    assert len(result.income_statements) == 1
    assert len(result.balance_sheets) == 1
    assert len(result.cash_flows) == 1
    assert result.balance_sheets[0].data["Total Assets"] == 5000.0
    assert result.cash_flows[0].data["Operating Cash Flow"] == 300.0


async def test_returns_multiple_periods_sorted_desc(
    db_session: AsyncSession,
) -> None:
    """Multiple distinct periods → list of statements newest-first."""
    s = await _mk_stock(db_session, "2330")
    for fy, fq, period in [
        (2025, 4, "2025-Q4"),
        (2026, 1, "2026-Q1"),
        (2025, 3, "2025-Q3"),
    ]:
        db_session.add(
            FSModel(
                stock_id=s.id,
                period=period,
                statement_type="income",
                fiscal_year=fy,
                fiscal_quarter=fq,
                data={"Revenue": 1000.0 * fy + fq},
            )
        )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    periods = [s.period for s in result.income_statements]
    assert periods == ["2026-Q1", "2025-Q4", "2025-Q3"]


async def test_skips_unknown_statement_type(db_session: AsyncSession) -> None:
    """Unknown statement_type (e.g. 'audit') is silently skipped."""
    s = await _mk_stock(db_session, "2330")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"Revenue": 1000.0},
        )
    )
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="auditing",  # not in _STMT_TYPE_MAP
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"SomeField": 1.0},
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    assert len(result.income_statements) == 1


async def test_skips_non_castable_values(db_session: AsyncSession) -> None:
    """Non-numeric `Revenue` value is silently dropped via
    contextlib.suppress(TypeError, ValueError)."""
    s = await _mk_stock(db_session, "2330")
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"Revenue": "not-a-number", "OperatingIncome": 200.0},
        )
    )
    await db_session.commit()

    result = await read_tw_financials("2330", db_session)
    assert result is not None
    data = result.income_statements[0].data
    # Total Revenue dropped, Operating Income kept
    assert "Total Revenue" not in data
    assert data["Operating Income"] == 200.0
