"""Taiwan stock earnings calendar service.

Taiwan regulatory filing deadlines (TWSE/GTSM):
  Q1 (period ending Mar 31) → deadline May 15 of same year
  Q2 (period ending Jun 30) → deadline Aug 14 of same year
  Q3 (period ending Sep 30) → deadline Nov 14 of same year
  Q4 (period ending Dec 31) → deadline Mar 31 of following year
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.financial_statement import FinancialStatement as FSModel
from app.models.stock import Stock

logger = structlog.get_logger()

# Q → (month, day) of deadline within the same year (Q4 uses next year)
_DEADLINE: dict[int, tuple[int, int]] = {
    1: (5, 15),
    2: (8, 14),
    3: (11, 14),
    4: (3, 31),   # next calendar year
}

# Q → period-end date within fiscal year
_PERIOD_END: dict[int, tuple[int, int]] = {
    1: (3, 31),
    2: (6, 30),
    3: (9, 30),
    4: (12, 31),
}


@dataclass(frozen=True)
class EarningsEvent:
    """One upcoming or recent earnings filing event."""
    symbol: str
    fiscal_year: int
    fiscal_quarter: int
    period_label: str        # e.g. "2025-Q4"
    period_end_date: date
    deadline_date: date
    days_until_deadline: int  # negative = already past deadline
    already_in_db: bool


def _deadline_for(fiscal_year: int, quarter: int) -> date:
    month, day = _DEADLINE[quarter]
    year = fiscal_year + 1 if quarter == 4 else fiscal_year
    return date(year, month, day)


def _period_end_for(fiscal_year: int, quarter: int) -> date:
    month, day = _PERIOD_END[quarter]
    return date(fiscal_year, month, day)


def _current_expected_quarter(today: date) -> tuple[int, int]:
    """Return (fiscal_year, quarter) of the most recently ended quarter."""
    if today.month <= 3:
        return today.year - 1, 4
    elif today.month <= 6:
        return today.year, 1
    elif today.month <= 9:
        return today.year, 2
    else:
        return today.year, 3


class EarningsCalendarService:
    """Calculate upcoming earnings filing dates for Taiwan stocks."""

    async def get_calendar(
        self,
        symbol: str,
        db: AsyncSession,
        today: date | None = None,
        lookahead_quarters: int = 2,
    ) -> list[EarningsEvent]:
        """
        Return the next `lookahead_quarters` expected filing events for a stock.

        Each event tells you:
        - Which quarter is expected
        - The regulatory deadline
        - Days until deadline (negative if overdue)
        - Whether data is already in our DB
        """
        if today is None:
            today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()

        # Resolve stock
        stock_q = await db.execute(
            select(Stock).where(
                Stock.symbol.in_([symbol, f"{symbol}.TW"])
            ).limit(1)
        )
        stock = stock_q.scalar_one_or_none()

        # Periods already in DB (income statements as proxy)
        periods_in_db: set[str] = set()
        if stock is not None:
            db_q = await db.execute(
                select(FSModel.period)
                .where(
                    FSModel.stock_id == stock.id,
                    FSModel.statement_type == "income",
                )
            )
            periods_in_db = {row[0] for row in db_q.fetchall()}

        # Build upcoming events starting from the most recently ended quarter
        fy, q = _current_expected_quarter(today)
        events: list[EarningsEvent] = []

        for _ in range(lookahead_quarters):
            period_label = f"{fy}-Q{q}"
            deadline = _deadline_for(fy, q)
            period_end = _period_end_for(fy, q)
            days_until = (deadline - today).days

            events.append(EarningsEvent(
                symbol=symbol,
                fiscal_year=fy,
                fiscal_quarter=q,
                period_label=period_label,
                period_end_date=period_end,
                deadline_date=deadline,
                days_until_deadline=days_until,
                already_in_db=period_label in periods_in_db,
            ))

            # Advance one quarter forward
            if q == 4:
                q, fy = 1, fy + 1
            else:
                q += 1

        return events

    async def get_latest_filed_period(
        self,
        symbol: str,
        db: AsyncSession,
    ) -> str | None:
        """Return the most recent period label in DB for this stock, or None."""
        stock_q = await db.execute(
            select(Stock).where(
                Stock.symbol.in_([symbol, f"{symbol}.TW"])
            ).limit(1)
        )
        stock = stock_q.scalar_one_or_none()
        if stock is None:
            return None

        result = await db.execute(
            select(FSModel.period)
            .where(
                FSModel.stock_id == stock.id,
                FSModel.statement_type == "income",
            )
            .order_by(
                FSModel.fiscal_year.desc(),
                FSModel.fiscal_quarter.desc(),
            )
            .limit(1)
        )
        row = result.fetchone()
        return row[0] if row else None
