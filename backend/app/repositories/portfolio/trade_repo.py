"""PortfolioTradeRepo — CRUD over `portfolio_trades`.

User isolation: trade rows do not carry `user_id` directly. Every
method that takes `user_id` enforces it via JOIN to `portfolio_accounts`.
Per §5.3 + §11 R3, no business logic here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update

from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.trade import PortfolioTrade

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PortfolioTradeRepo:
    """CRUD-only repo. FIFO / cost-basis / tier checks live elsewhere."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        account_id: int,
        user_id: int,
        **trade_fields: Any,
    ) -> PortfolioTrade | None:
        """Insert a trade after verifying the parent account belongs to
        `user_id`. Returns None if the account is not owned by user
        (caller should treat as 404 / 403 — repo does not raise)."""
        owner_ok = await self.db.execute(
            select(PortfolioAccount.id).where(
                PortfolioAccount.id == account_id,
                PortfolioAccount.user_id == user_id,
            )
        )
        if owner_ok.scalar_one_or_none() is None:
            return None
        trade = PortfolioTrade(account_id=account_id, **trade_fields)
        self.db.add(trade)
        await self.db.flush()
        await self.db.refresh(trade)
        return trade

    async def get_by_id(self, trade_id: int, user_id: int) -> PortfolioTrade | None:
        """Fetch trade only if its parent account belongs to `user_id`."""
        result = await self.db.execute(
            select(PortfolioTrade)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioTrade.account_id,
            )
            .where(
                PortfolioTrade.id == trade_id,
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
    ) -> list[PortfolioTrade]:
        """Recent trades on `account_id`, filtered by ownership. Ordered by
        trade_date DESC then id DESC (latest first)."""
        result = await self.db.execute(
            select(PortfolioTrade)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioTrade.account_id,
            )
            .where(
                PortfolioTrade.account_id == account_id,
                PortfolioAccount.user_id == user_id,
            )
            .order_by(PortfolioTrade.trade_date.desc(), PortfolioTrade.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user_this_month(self, user_id: int) -> int:
        """Trades created across the user's accounts since the start of the
        current UTC month — for tier quota (counted on `trade_date`, not
        `created_at`, per spec §6 schema semantics)."""
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()
        result = await self.db.execute(
            select(func.count(PortfolioTrade.id))
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioTrade.account_id,
            )
            .where(
                PortfolioAccount.user_id == user_id,
                PortfolioTrade.trade_date >= month_start,
            )
        )
        return int(result.scalar() or 0)

    async def update(self, trade_id: int, user_id: int, **fields: Any) -> PortfolioTrade | None:
        """Patch a trade if it belongs to `user_id`'s account.

        Note: callers (services) are responsible for rebuilding lots /
        positions after a PATCH. This repo only updates the row.
        """
        existing = await self.get_by_id(trade_id, user_id)
        if existing is None:
            return None
        valid_cols = {
            c.key
            for c in PortfolioTrade.__table__.columns
            if c.key not in {"id", "account_id", "created_at", "updated_at"}
        }
        patch = {k: v for k, v in fields.items() if k in valid_cols}
        if not patch:
            return existing
        await self.db.execute(
            update(PortfolioTrade).where(PortfolioTrade.id == trade_id).values(**patch)
        )
        await self.db.flush()
        return await self.get_by_id(trade_id, user_id)

    async def delete(self, trade_id: int, user_id: int) -> bool:
        """Delete the trade iff its parent account belongs to `user_id`.
        Cascades to lots via FK. Position rebuild is the service layer's job."""
        existing = await self.get_by_id(trade_id, user_id)
        if existing is None:
            return False
        await self.db.execute(delete(PortfolioTrade).where(PortfolioTrade.id == trade_id))
        await self.db.flush()
        return True
