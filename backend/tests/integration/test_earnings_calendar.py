"""Integration tests for EarningsCalendarService — Taiwan stock earnings
deadline calculator. Pure date arithmetic + a single ORM lookup."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.financial_statement import FinancialStatement as FSModel
from app.models.stock import Stock
from app.modules.financial_analysis.earnings_calendar import (
    EarningsCalendarService,
    _current_expected_quarter,
    _deadline_for,
    _period_end_for,
)

# ── _deadline_for / _period_end_for ───────────────────────────────────────


def test_deadline_q1() -> None:
    assert _deadline_for(2026, 1) == date(2026, 5, 15)


def test_deadline_q2() -> None:
    assert _deadline_for(2026, 2) == date(2026, 8, 14)


def test_deadline_q3() -> None:
    assert _deadline_for(2026, 3) == date(2026, 11, 14)


def test_deadline_q4_carries_into_next_year() -> None:
    """Q4 deadline is March 31 of the following calendar year."""
    assert _deadline_for(2026, 4) == date(2027, 3, 31)


def test_period_end_q1() -> None:
    assert _period_end_for(2026, 1) == date(2026, 3, 31)


def test_period_end_q4() -> None:
    assert _period_end_for(2026, 4) == date(2026, 12, 31)


# ── _current_expected_quarter ─────────────────────────────────────────────


def test_current_quarter_jan_returns_prev_year_q4() -> None:
    """January = before Q1 deadline, last ended quarter is prior year's Q4."""
    assert _current_expected_quarter(date(2026, 1, 15)) == (2025, 4)


def test_current_quarter_march_still_prev_year_q4() -> None:
    assert _current_expected_quarter(date(2026, 3, 1)) == (2025, 4)


def test_current_quarter_april_returns_this_year_q1() -> None:
    assert _current_expected_quarter(date(2026, 4, 1)) == (2026, 1)


def test_current_quarter_july_returns_q2() -> None:
    assert _current_expected_quarter(date(2026, 7, 1)) == (2026, 2)


def test_current_quarter_october_returns_q3() -> None:
    assert _current_expected_quarter(date(2026, 10, 1)) == (2026, 3)


# ── EarningsCalendarService.get_calendar ──────────────────────────────────


async def test_get_calendar_unknown_symbol_returns_2_events_with_in_db_false(
    db_session: AsyncSession,
) -> None:
    """Stock not in DB → still computes the 2 upcoming events, all
    `already_in_db=False`."""
    svc = EarningsCalendarService()
    events = await svc.get_calendar("9999", db_session, today=date(2026, 5, 1))
    assert len(events) == 2
    for e in events:
        assert e.already_in_db is False


async def test_get_calendar_known_stock_marks_already_in_db(
    db_session: AsyncSession,
) -> None:
    """When DB has the period's income statement, the event flips
    already_in_db=True."""
    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={"Revenue": 1000},
        )
    )
    await db_session.commit()

    svc = EarningsCalendarService()
    events = await svc.get_calendar("2330", db_session, today=date(2026, 4, 1))
    assert len(events) == 2
    q1_event = next(e for e in events if e.period_label == "2026-Q1")
    assert q1_event.already_in_db is True
    q2_event = next(e for e in events if e.period_label == "2026-Q2")
    assert q2_event.already_in_db is False


async def test_get_calendar_lookahead_quarters_param(
    db_session: AsyncSession,
) -> None:
    """lookahead_quarters=4 → 4 events spanning Q-quarters in sequence."""
    svc = EarningsCalendarService()
    events = await svc.get_calendar(
        "9999", db_session, today=date(2026, 5, 1), lookahead_quarters=4
    )
    assert len(events) == 4
    labels = [e.period_label for e in events]
    assert labels == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]


async def test_get_calendar_rolls_into_next_year(
    db_session: AsyncSession,
) -> None:
    """Starting from Q3 with lookahead=4 should cross the year boundary."""
    svc = EarningsCalendarService()
    events = await svc.get_calendar(
        "9999", db_session, today=date(2026, 10, 1), lookahead_quarters=4
    )
    labels = [e.period_label for e in events]
    assert labels == ["2026-Q3", "2026-Q4", "2027-Q1", "2027-Q2"]


async def test_get_calendar_days_until_deadline_negative_for_overdue(
    db_session: AsyncSession,
) -> None:
    """Today=2026-06-01, Q1 deadline 2026-05-15 → days_until_deadline negative."""
    svc = EarningsCalendarService()
    events = await svc.get_calendar("9999", db_session, today=date(2026, 6, 1))
    q1 = next(e for e in events if e.period_label == "2026-Q1")
    assert q1.days_until_deadline < 0


async def test_get_calendar_resolves_dot_tw_suffix(db_session: AsyncSession) -> None:
    """Symbol "2330" looks up either "2330" or "2330.TW" in DB."""
    s = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="income",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={},
        )
    )
    await db_session.commit()

    svc = EarningsCalendarService()
    events = await svc.get_calendar("2330", db_session, today=date(2026, 4, 1))
    q1 = next(e for e in events if e.period_label == "2026-Q1")
    assert q1.already_in_db is True


# ── get_latest_filed_period ───────────────────────────────────────────────


async def test_get_latest_filed_period_unknown_symbol_none(
    db_session: AsyncSession,
) -> None:
    svc = EarningsCalendarService()
    assert await svc.get_latest_filed_period("9999", db_session) is None


async def test_get_latest_filed_period_returns_most_recent(
    db_session: AsyncSession,
) -> None:
    """ORDER BY fiscal_year DESC, fiscal_quarter DESC → highest wins."""
    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
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
                data={},
            )
        )
    await db_session.commit()

    svc = EarningsCalendarService()
    latest = await svc.get_latest_filed_period("2330", db_session)
    assert latest == "2026-Q1"


async def test_get_latest_filed_period_no_income_stmt_returns_none(
    db_session: AsyncSession,
) -> None:
    """Stock exists but no income-type rows → None."""
    s = Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    # Only a balance sheet row
    db_session.add(
        FSModel(
            stock_id=s.id,
            period="2026-Q1",
            statement_type="balance",
            fiscal_year=2026,
            fiscal_quarter=1,
            data={},
        )
    )
    await db_session.commit()

    svc = EarningsCalendarService()
    assert await svc.get_latest_filed_period("2330", db_session) is None
