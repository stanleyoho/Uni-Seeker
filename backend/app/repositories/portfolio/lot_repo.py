"""PortfolioLotRepo — CRUD over `portfolio_lots`.

Per spec §5.3 + §11 R3, this repo does NOT run FIFO. It only:
  - inserts lot rows;
  - retrieves open lots in FIFO order (oldest trade_id first);
  - persists `remaining_qty` / `is_exhausted` updates that a FIFO
    engine (`app.modules.trade_journal.fifo_engine`) computes in
    pure Python land.

FIFO algorithm lives in the domain layer; this is purely persistence.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import case, delete, select, update

from app.db.models.portfolio.lot import PortfolioLot

if TYPE_CHECKING:
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession


class PortfolioLotRepo:
    """CRUD-only repo. FIFO consumption order is computed elsewhere."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, trade_id: int, **lot_fields: Any) -> PortfolioLot:
        """Insert a single lot row tied to `trade_id`. Caller (service
        layer) provides account_id / symbol / market / qty / cost."""
        lot = PortfolioLot(trade_id=trade_id, **lot_fields)
        self.db.add(lot)
        await self.db.flush()
        await self.db.refresh(lot)
        return lot

    async def list_open_for_position(
        self, account_id: int, symbol: str, market: Any | None = None
    ) -> list[PortfolioLot]:
        """All non-exhausted lots for a position, in FIFO consumption order
        (oldest lot id first).

        Note: spec signature uses `stock_id: str` in the task brief, but
        the schema actually stores `symbol` + `market` (spec §6 Table 3).
        We follow the schema. `market` is optional for legacy / single-
        market callers; pass it to be safe.
        """
        stmt = (
            select(PortfolioLot)
            .where(
                PortfolioLot.account_id == account_id,
                PortfolioLot.symbol == symbol,
                PortfolioLot.is_exhausted.is_(False),
            )
            .order_by(PortfolioLot.id.asc())
        )
        if market is not None:
            stmt = stmt.where(PortfolioLot.market == market)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_remaining(
        self, lot_id: int, remaining_qty: Decimal, is_exhausted: bool
    ) -> None:
        """Persist the result of a FIFO consumption step for ONE lot.

        For bulk SELL rebuilds, prefer `bulk_update` to avoid N round
        trips."""
        await self.db.execute(
            update(PortfolioLot)
            .where(PortfolioLot.id == lot_id)
            .values(remaining_qty=remaining_qty, is_exhausted=is_exhausted)
        )
        await self.db.flush()

    async def bulk_update(
        self, lots: list[tuple[int, Decimal, bool]]
    ) -> None:
        """Persist many lot updates in a single SQL round trip.

        `lots` is a list of (lot_id, remaining_qty, is_exhausted) tuples
        produced by FIFOEngine. Implemented via a single `UPDATE ... CASE
        WHEN id = ... THEN ...` statement so all rows land atomically
        inside the same transaction. Empty input is a no-op.

        Rationale: `bulk_update_mappings` would be the natural SQLAlchemy
        choice, but on AsyncSession it requires `session.run_sync(...)`
        and bypasses the unit-of-work, making test introspection harder.
        A single parametrized UPDATE is portable (PG + SQLite) and clearer.
        """
        if not lots:
            return
        ids = [lot_id for lot_id, _, _ in lots]
        qty_case = case(
            *[(PortfolioLot.id == lot_id, qty) for lot_id, qty, _ in lots],
            else_=PortfolioLot.remaining_qty,
        )
        exhausted_case = case(
            *[(PortfolioLot.id == lot_id, flag) for lot_id, _, flag in lots],
            else_=PortfolioLot.is_exhausted,
        )
        await self.db.execute(
            update(PortfolioLot)
            .where(PortfolioLot.id.in_(ids))
            .values(remaining_qty=qty_case, is_exhausted=exhausted_case)
        )
        await self.db.flush()

    async def delete_by_trade(self, trade_id: int) -> None:
        """Wipe all lots produced by `trade_id`. Used by trade PATCH /
        DELETE to rebuild the lot chain from scratch."""
        await self.db.execute(
            delete(PortfolioLot).where(PortfolioLot.trade_id == trade_id)
        )
        await self.db.flush()
