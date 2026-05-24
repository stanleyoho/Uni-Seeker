"""PortfolioDividendRepo — CRUD over `portfolio_dividends`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.3.

User isolation: dividend rows do not carry `user_id` directly. Every
method that takes `user_id` enforces it via JOIN to `portfolio_accounts`,
mirroring the `PortfolioTradeRepo` pattern. Per §5.3 + §11 R3, no
business logic (cost-basis effect, tier check) lives here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update

from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.dividend import PortfolioDividend

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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
