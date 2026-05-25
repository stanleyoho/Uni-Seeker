"""PortfolioAccountRepo — CRUD over `portfolio_accounts`.

Structural user isolation: every method takes `user_id` and applies it
as a WHERE clause. Cross-user reads / writes are impossible by
construction (Phase 1 anti-coupling rule §11 R3 + §5.3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, update

from app.db.models.portfolio.account import PortfolioAccount

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PortfolioAccountRepo:
    """CRUD-only repo. No business logic, no tier checks."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: int,
        name: str,
        market: Any,
        broker: str | None = None,
        currency: str = "TWD",
        description: str | None = None,
    ) -> PortfolioAccount:
        """Insert a new account for `user_id`. Flushes but does not commit."""
        account = PortfolioAccount(
            user_id=user_id,
            name=name,
            market=market,
            currency=currency,
            broker=broker,
            description=description,
        )
        self.db.add(account)
        await self.db.flush()
        await self.db.refresh(account)
        return account

    async def get_by_id(self, account_id: int, user_id: int) -> PortfolioAccount | None:
        """Fetch one row only if it belongs to `user_id`."""
        result = await self.db.execute(
            select(PortfolioAccount).where(
                PortfolioAccount.id == account_id,
                PortfolioAccount.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int) -> list[PortfolioAccount]:
        """All accounts owned by `user_id`, oldest first."""
        result = await self.db.execute(
            select(PortfolioAccount)
            .where(PortfolioAccount.user_id == user_id)
            .order_by(PortfolioAccount.id.asc())
        )
        return list(result.scalars().all())

    async def update(self, account_id: int, user_id: int, **fields: Any) -> PortfolioAccount | None:
        """Patch `fields` on the row iff it belongs to `user_id`.

        Returns the updated row, or None if it was not found / not owned.
        Only mapped column attributes that exist on the model are applied;
        unknown keys are silently dropped (defensive — callers should use
        Pydantic to pre-validate, this is a last line of defense).
        """
        if not fields:
            return await self.get_by_id(account_id, user_id)
        valid_cols = {
            c.key
            for c in PortfolioAccount.__table__.columns
            if c.key not in {"id", "user_id", "created_at"}
        }
        patch = {k: v for k, v in fields.items() if k in valid_cols}
        if not patch:
            return await self.get_by_id(account_id, user_id)
        await self.db.execute(
            update(PortfolioAccount)
            .where(
                PortfolioAccount.id == account_id,
                PortfolioAccount.user_id == user_id,
            )
            .values(**patch)
        )
        await self.db.flush()
        return await self.get_by_id(account_id, user_id)

    async def delete(self, account_id: int, user_id: int) -> bool:
        """Delete the row iff it belongs to `user_id`. Cascades to trades /
        lots / positions via ORM FK. Returns True if a row was deleted."""
        result = await self.db.execute(
            delete(PortfolioAccount).where(
                PortfolioAccount.id == account_id,
                PortfolioAccount.user_id == user_id,
            )
        )
        await self.db.flush()
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]

    async def count_by_user(self, user_id: int) -> int:
        """Number of accounts owned by `user_id` — for tier quota checks
        (which live in service / billing layer)."""
        result = await self.db.execute(
            select(func.count(PortfolioAccount.id)).where(PortfolioAccount.user_id == user_id)
        )
        return int(result.scalar() or 0)
