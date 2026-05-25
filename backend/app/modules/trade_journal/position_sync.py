"""Apply FIFO engine results to the database (trade_lots + positions tables)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import Position, Trade, TradeLot
from app.modules.trade_journal.fifo_engine import FIFOEngine, Lot


async def _load_open_lots(
    db: AsyncSession,
    account_id: int,
    symbol: str,
    market: str,
) -> list[Lot]:
    """Fetch open (non-exhausted) lots in FIFO order (oldest trade_id first)."""
    stmt = (
        select(TradeLot)
        .where(
            TradeLot.account_id == account_id,
            TradeLot.symbol == symbol,
            TradeLot.market == market,
            TradeLot.is_exhausted.is_(False),
        )
        .order_by(TradeLot.trade_id.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        Lot(
            lot_id=row.id,
            original_qty=row.original_qty,
            remaining_qty=row.remaining_qty,
            cost_per_unit=row.cost_per_unit,
            is_exhausted=row.is_exhausted,
        )
        for row in rows
    ]


async def _upsert_position(
    db: AsyncSession,
    account_id: int,
    symbol: str,
    market: str,
    currency: str,
    qty_delta: Decimal,
    cost_delta: Decimal,
    realized_pnl_delta: Decimal,
) -> None:
    """Insert or update the positions cache row."""
    stmt = (
        pg_insert(Position)
        .values(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=currency,
            quantity=qty_delta,
            avg_cost_fifo=None,
            total_cost=cost_delta if cost_delta > Decimal("0") else Decimal("0"),
            realized_pnl=realized_pnl_delta,
            is_closed=False,
        )
        .on_conflict_do_update(
            index_elements=["account_id", "symbol", "market"],
            set_={
                "quantity": Position.quantity + qty_delta,
                "total_cost": sa_func.coalesce(Position.total_cost, Decimal("0")) + cost_delta,
                "realized_pnl": Position.realized_pnl + realized_pnl_delta,
                "last_updated": sa_func.now(),
            },
        )
    )
    await db.execute(stmt)

    # Recalculate avg_cost_fifo and is_closed after upsert
    pos_stmt = select(Position).where(
        Position.account_id == account_id,
        Position.symbol == symbol,
        Position.market == market,
    )
    pos = (await db.execute(pos_stmt)).scalar_one()
    if pos.quantity > Decimal("0") and pos.total_cost is not None:
        pos.avg_cost_fifo = pos.total_cost / pos.quantity
    pos.is_closed = pos.quantity <= Decimal("0")


async def apply_buy(
    db: AsyncSession,
    trade: Trade,
    currency: str,
) -> None:
    """Create a new lot and update position cache for a BUY trade.

    Domain invariant: BUY trades MUST have price + quantity set.
    The DB columns are nullable to accommodate DIVIDEND / SPLIT actions
    where one of those fields legitimately is absent.
    """
    assert trade.price is not None, "BUY trade must have price"
    assert trade.quantity is not None, "BUY trade must have quantity"
    price = trade.price
    quantity = trade.quantity
    cost_per_unit = (price * quantity + trade.fee) / quantity
    lot = TradeLot(
        trade_id=trade.id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        original_qty=quantity,
        remaining_qty=quantity,
        cost_per_unit=cost_per_unit,
    )
    db.add(lot)

    total_cost = cost_per_unit * quantity
    await _upsert_position(
        db,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        currency=currency,
        qty_delta=quantity,
        cost_delta=total_cost,
        realized_pnl_delta=Decimal("0"),
    )


async def apply_sell(
    db: AsyncSession,
    trade: Trade,
    currency: str,
) -> Decimal:
    """Consume open lots via FIFO and return realized_pnl.

    Domain invariant: SELL trades MUST have price + quantity set.
    """
    assert trade.price is not None, "SELL trade must have price"
    assert trade.quantity is not None, "SELL trade must have quantity"
    quantity = trade.quantity
    open_lots = await _load_open_lots(db, trade.account_id, trade.symbol, trade.market)
    engine = FIFOEngine(open_lots=open_lots)
    result = engine.process_sell(
        qty=quantity,
        price=trade.price,
        fee=trade.fee,
        tax=trade.tax,
    )

    # Build a set of lot_ids for ONLY lots that actually changed
    # (is_exhausted=True or remaining_qty decreased from original_qty)
    changed_lot_ids = {
        lot.lot_id
        for lot in result.updated_lots
        if lot.is_exhausted or lot.remaining_qty < lot.original_qty
    }

    if changed_lot_ids:
        db_lots_stmt = select(TradeLot).where(TradeLot.id.in_(list(changed_lot_ids)))
        db_lots = (await db.execute(db_lots_stmt)).scalars().all()
        lot_map = {lot.lot_id: lot for lot in result.updated_lots}
        for db_lot in db_lots:
            updated = lot_map[db_lot.id]
            db_lot.remaining_qty = updated.remaining_qty
            db_lot.is_exhausted = updated.is_exhausted

    # Compute cost consumed: sum(cost_per_unit * shares_consumed) for each changed lot
    cost_consumed = Decimal("0")
    for lot in result.updated_lots:
        if lot.lot_id in changed_lot_ids:
            # shares consumed = original_qty - remaining_qty (engine mutated remaining_qty)
            shares_consumed = lot.original_qty - lot.remaining_qty
            cost_consumed += lot.cost_per_unit * shares_consumed

    await _upsert_position(
        db,
        account_id=trade.account_id,
        symbol=trade.symbol,
        market=trade.market,
        currency=currency,
        qty_delta=-quantity,
        cost_delta=-cost_consumed,
        realized_pnl_delta=result.realized_pnl,
    )

    return result.realized_pnl


async def apply_split(
    db: AsyncSession,
    trade: Trade,
    split_ratio: Decimal,
) -> None:
    """Apply a stock split to all open lots and position for this account+symbol+market."""
    open_lots = await _load_open_lots(db, trade.account_id, trade.symbol, trade.market)
    engine = FIFOEngine(open_lots=open_lots)
    updated_lots = engine.process_split(ratio=split_ratio)

    lot_map = {lot.lot_id: lot for lot in updated_lots}
    db_lots_stmt = select(TradeLot).where(
        TradeLot.account_id == trade.account_id,
        TradeLot.symbol == trade.symbol,
        TradeLot.market == trade.market,
        TradeLot.is_exhausted.is_(False),
    )
    db_lots = (await db.execute(db_lots_stmt)).scalars().all()
    for db_lot in db_lots:
        if db_lot.id in lot_map:
            u = lot_map[db_lot.id]
            db_lot.remaining_qty = u.remaining_qty
            db_lot.original_qty = u.original_qty
            db_lot.cost_per_unit = u.cost_per_unit

    # Update position quantity and avg_cost_fifo
    pos_stmt = select(Position).where(
        Position.account_id == trade.account_id,
        Position.symbol == trade.symbol,
        Position.market == trade.market,
    )
    pos = (await db.execute(pos_stmt)).scalar_one_or_none()
    if pos:
        pos.quantity = pos.quantity * split_ratio
        if pos.total_cost and pos.quantity > Decimal("0"):
            pos.avg_cost_fifo = pos.total_cost / pos.quantity
