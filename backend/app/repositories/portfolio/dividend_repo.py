"""PortfolioDividendRepo — CRUD over `portfolio_dividends`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.3.

User isolation: dividend rows do not carry `user_id` directly. Every
method that takes `user_id` enforces it via JOIN to `portfolio_accounts`,
mirroring the `PortfolioTradeRepo` pattern. Per §5.3 + §11 R3, no
business logic (cost-basis effect, tier check) lives here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple

from sqlalchemy import case, delete, func, select, update

from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.dividend import PortfolioDividend

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class MonthlyDividendSummary(NamedTuple):
    """Aggregated dividend income for one calendar month.

    Money figures (`gross_amount` / `net_amount`) count CASH dividends
    ONLY — STOCK 配股 `amount_per_share` is a ratio, not cash, so it is
    excluded from the income total (婆媽 widget shows "本月股息收入" =
    cash actually received). `stock_count` is surfaced separately so the
    UI can optionally show "本月配股 N 筆" without polluting the cash sum.

    The "本月" basis is the date cash is *received*: `pay_date` when set,
    falling back to `ex_dividend_date` when `pay_date` is NULL.
    """

    month: str  # "YYYY-MM" of the queried window, for display / sanity.
    gross_amount: Decimal  # Σ amount_per_share × quantity_at_record (CASH).
    net_amount: Decimal  # gross − withholding_tax (CASH).
    cash_count: int  # number of CASH dividend rows in the window.
    stock_count: int  # number of STOCK 配股 rows in the window (badge only).


class PortfolioDividendRepo:
    """CRUD-only repo for portfolio_dividends. No cost-basis math."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        account_id: int,
        user_id: int,
        **dividend_fields: Any,
    ) -> PortfolioDividend | None:
        """Insert a dividend row after verifying the parent account belongs
        to `user_id`. Returns None if the account is not owned by user
        (caller should treat as 404 / 403 — repo does not raise).
        """
        owner_ok = await self.db.execute(
            select(PortfolioAccount.id).where(
                PortfolioAccount.id == account_id,
                PortfolioAccount.user_id == user_id,
            )
        )
        if owner_ok.scalar_one_or_none() is None:
            return None
        dividend = PortfolioDividend(account_id=account_id, **dividend_fields)
        self.db.add(dividend)
        await self.db.flush()
        await self.db.refresh(dividend)
        return dividend

    async def get_by_id(self, dividend_id: int, user_id: int) -> PortfolioDividend | None:
        """Fetch dividend only if its parent account belongs to `user_id`."""
        result = await self.db.execute(
            select(PortfolioDividend)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioDividend.account_id,
            )
            .where(
                PortfolioDividend.id == dividend_id,
                PortfolioAccount.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_account(
        self,
        account_id: int,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PortfolioDividend]:
        """Recent dividends on `account_id`, scoped to owner. Ordered by
        ex_dividend_date DESC then id DESC (latest first)."""
        result = await self.db.execute(
            select(PortfolioDividend)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioDividend.account_id,
            )
            .where(
                PortfolioDividend.account_id == account_id,
                PortfolioAccount.user_id == user_id,
            )
            .order_by(
                PortfolioDividend.ex_dividend_date.desc(),
                PortfolioDividend.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_by_user(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> list[PortfolioDividend]:
        """All dividends across `user_id`'s accounts. Joins on
        portfolio_accounts to enforce ownership; ordered ex_dividend_date
        DESC."""
        result = await self.db.execute(
            select(PortfolioDividend)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioDividend.account_id,
            )
            .where(PortfolioAccount.user_id == user_id)
            .order_by(
                PortfolioDividend.ex_dividend_date.desc(),
                PortfolioDividend.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update(
        self, dividend_id: int, user_id: int, **fields: Any
    ) -> PortfolioDividend | None:
        """Patch a dividend row iff it belongs to `user_id`'s account.

        Mirrors `PortfolioTradeRepo.update`: silently drops unknown /
        immutable keys (allowlist of mapped columns minus id /
        account_id / created_at / updated_at). Callers (services) are
        responsible for any cost-basis reversal — this repo only updates
        the row.
        """
        existing = await self.get_by_id(dividend_id, user_id)
        if existing is None:
            return None
        valid_cols = {
            c.key
            for c in PortfolioDividend.__table__.columns
            if c.key not in {"id", "account_id", "created_at", "updated_at"}
        }
        patch = {k: v for k, v in fields.items() if k in valid_cols}
        if not patch:
            return existing
        await self.db.execute(
            update(PortfolioDividend).where(PortfolioDividend.id == dividend_id).values(**patch)
        )
        await self.db.flush()
        return await self.get_by_id(dividend_id, user_id)

    async def delete(self, dividend_id: int, user_id: int) -> bool:
        """Delete the dividend iff its parent account belongs to `user_id`.
        Returns True on hit, False on miss / cross-user."""
        existing = await self.get_by_id(dividend_id, user_id)
        if existing is None:
            return False
        await self.db.execute(delete(PortfolioDividend).where(PortfolioDividend.id == dividend_id))
        await self.db.flush()
        return True

    async def count_by_user_this_month(self, user_id: int) -> int:
        """Dividends with `ex_dividend_date` in the current UTC month
        across the user's accounts — exposed for future tier quotas if
        we ever cap monthly dividend records."""
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()
        result = await self.db.execute(
            select(func.count(PortfolioDividend.id))
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioDividend.account_id,
            )
            .where(
                PortfolioAccount.user_id == user_id,
                PortfolioDividend.ex_dividend_date >= month_start,
            )
        )
        return int(result.scalar() or 0)

    async def get_monthly_dividend_summary(
        self, user_id: int, *, today: date | None = None
    ) -> MonthlyDividendSummary:
        """Aggregate the user's dividend income for the current calendar
        month (本月股息收入 widget).

        "本月" basis = the date cash is received: ``pay_date`` when set,
        falling back to ``ex_dividend_date`` when ``pay_date`` is NULL
        (``COALESCE(pay_date, ex_dividend_date)``). The window is
        ``[month_start, next_month_start)`` of `today` (defaults to the
        current UTC date; injectable for deterministic tests).

        Money figures count CASH dividends ONLY — STOCK 配股 stores a
        ratio in ``amount_per_share`` (not cash), so summing it would be
        meaningless. STOCK rows are counted separately into
        ``stock_count`` for an optional badge.

        Performed as a single grouped query (no per-row Python) so the
        I/O cost is one round trip regardless of dividend volume.
        """
        now_date = today or datetime.now(UTC).date()
        month_start = now_date.replace(day=1)
        # First day of next month, handling the December → January roll.
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)

        received_date = func.coalesce(
            PortfolioDividend.pay_date, PortfolioDividend.ex_dividend_date
        )
        gross_expr = PortfolioDividend.amount_per_share * PortfolioDividend.quantity_at_record
        is_cash = PortfolioDividend.dividend_type == "CASH"

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(case((is_cash, gross_expr), else_=0)),
                    0,
                ).label("gross"),
                func.coalesce(
                    func.sum(
                        case(
                            (is_cash, gross_expr - PortfolioDividend.withholding_tax),
                            else_=0,
                        )
                    ),
                    0,
                ).label("net"),
                func.coalesce(func.sum(case((is_cash, 1), else_=0)), 0).label("cash_count"),
                func.coalesce(
                    func.sum(case((PortfolioDividend.dividend_type == "STOCK", 1), else_=0)),
                    0,
                ).label("stock_count"),
            )
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioDividend.account_id,
            )
            .where(
                PortfolioAccount.user_id == user_id,
                received_date >= month_start,
                received_date < next_month_start,
            )
        )
        row = result.one()
        return MonthlyDividendSummary(
            month=month_start.strftime("%Y-%m"),
            gross_amount=Decimal(str(row.gross)),
            net_amount=Decimal(str(row.net)),
            cash_count=int(row.cash_count),
            stock_count=int(row.stock_count),
        )
