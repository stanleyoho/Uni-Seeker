"""PortfolioPositionRepo — CRUD + upsert over `portfolio_positions`.

User isolation: positions are scoped by `account_id`. Cross-user
`list_by_user` / `count_by_user` use a JOIN on `portfolio_accounts`
to enforce ownership. Per §5.3 + §11 R3, no P&L / cost-basis logic
runs here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.position import PortfolioPosition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class PortfolioPositionRepo:
    """CRUD + idempotent upsert. Roll-up math lives in service layer."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self,
        account_id: int,
        symbol: str,
        market: Any,
        currency: str,
        quantity: Decimal,
        avg_cost: Decimal | None,
        total_cost: Decimal | None = None,
        realized_pnl: Decimal = Decimal("0"),
        is_closed: bool = False,
    ) -> PortfolioPosition:
        """Insert-or-update on `(account_id, symbol, market)`.

        Uses the dialect-native ON CONFLICT clause when available
        (PostgreSQL prod, SQLite test). Both dialects ship a compatible
        `insert(...).on_conflict_do_update(...)` builder, so the same
        codepath works in tests.
        """
        bind = self.db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")

        values = {
            "account_id": account_id,
            "symbol": symbol,
            "market": market,
            "currency": currency,
            "quantity": quantity,
            "avg_cost_fifo": avg_cost,
            "total_cost": total_cost,
            "realized_pnl": realized_pnl,
            "is_closed": is_closed,
        }

        if dialect_name == "postgresql":
            stmt = pg_insert(PortfolioPosition).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id", "symbol", "market"],
                set_={
                    "currency": stmt.excluded.currency,
                    "quantity": stmt.excluded.quantity,
                    "avg_cost_fifo": stmt.excluded.avg_cost_fifo,
                    "total_cost": stmt.excluded.total_cost,
                    "realized_pnl": stmt.excluded.realized_pnl,
                    "is_closed": stmt.excluded.is_closed,
                },
            )
        else:
            # SQLite (tests) — same `on_conflict_do_update` shape.
            # (sqlite_insert and pg_insert return different dialect-
            # specific Insert subclasses; mypy cannot unify them on the
            # same `stmt` local, so the assignment carries a noqa.)
            stmt = sqlite_insert(PortfolioPosition).values(**values)  # type: ignore[assignment]
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id", "symbol", "market"],
                set_={
                    "currency": stmt.excluded.currency,
                    "quantity": stmt.excluded.quantity,
                    "avg_cost_fifo": stmt.excluded.avg_cost_fifo,
                    "total_cost": stmt.excluded.total_cost,
                    "realized_pnl": stmt.excluded.realized_pnl,
                    "is_closed": stmt.excluded.is_closed,
                },
            )
        await self.db.execute(stmt)
        await self.db.flush()
        # Fetch the row back — we cannot rely on RETURNING for the SQLite
        # path uniformly. Expire any cached instance in the session
        # identity map first, otherwise an upsert that mutated an existing
        # row would silently return the stale Python object.
        existing = await self.get(account_id, symbol, market)
        if existing is not None:
            await self.db.refresh(existing)
            return existing
        # Post-upsert this should always exist; surface a clear error if not.
        raise RuntimeError("PortfolioPositionRepo.upsert: row missing after upsert")

    async def get(
        self, account_id: int, symbol: str, market: Any | None = None
    ) -> PortfolioPosition | None:
        """Fetch one position row by its uniqueness key."""
        stmt = select(PortfolioPosition).where(
            PortfolioPosition.account_id == account_id,
            PortfolioPosition.symbol == symbol,
        )
        if market is not None:
            stmt = stmt.where(PortfolioPosition.market == market)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_by_account(self, account_id: int) -> list[PortfolioPosition]:
        """All positions on a single account (open + closed)."""
        result = await self.db.execute(
            select(PortfolioPosition)
            .where(PortfolioPosition.account_id == account_id)
            .order_by(PortfolioPosition.id.asc())
        )
        return list(result.scalars().all())

    async def list_by_user(self, user_id: int) -> list[PortfolioPosition]:
        """All positions across all of `user_id`'s accounts. Joins on
        `portfolio_accounts` to enforce ownership."""
        result = await self.db.execute(
            select(PortfolioPosition)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioPosition.account_id,
            )
            .where(PortfolioAccount.user_id == user_id)
            .order_by(PortfolioPosition.id.asc())
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: int) -> int:
        """Number of position rows across `user_id`'s accounts — for tier
        `max_unique_symbols` quota (note: count is per row, not per
        distinct symbol; service layer may need to refine)."""
        result = await self.db.execute(
            select(func.count(PortfolioPosition.id))
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioPosition.account_id,
            )
            .where(PortfolioAccount.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def delete(self, account_id: int, symbol: str, market: Any | None = None) -> None:
        """Remove a position row (typically when a stock is fully closed
        and the service decides to prune)."""
        stmt = delete(PortfolioPosition).where(
            PortfolioPosition.account_id == account_id,
            PortfolioPosition.symbol == symbol,
        )
        if market is not None:
            stmt = stmt.where(PortfolioPosition.market == market)
        await self.db.execute(stmt)
        await self.db.flush()
