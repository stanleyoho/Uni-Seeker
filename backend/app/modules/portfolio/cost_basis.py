"""Portfolio cost basis — pure functions over FIFO lots.

Thin wrapper around `app.modules.trade_journal.fifo_engine.FIFOEngine`
exposing a portfolio-friendly dataclass API. **No DB, no SQLAlchemy.**

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.1 / §7.2.

Reuses `Lot`, `FIFOResult`, and `InsufficientSharesError` from the trade journal
module — see that module's docstring: "Pure FIFO engine — no database, no side
effects". The schema-coupling concern is handled by re-exporting these types
through the domain layer rather than importing ORM models.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.trade_journal.fifo_engine import (
    FIFOEngine,
    FIFOResult,
    InsufficientSharesError,
    Lot,
)

__all__ = [
    "BuyResult",
    "CostBasisInputs",
    "FIFOResult",
    "InsufficientSharesError",
    "Lot",
    "SellResult",
    "apply_buy",
    "apply_sell",
    "average_cost",
]


@dataclass
class CostBasisInputs:
    """Inputs for `apply_sell` — open lots + sell-side trade params."""

    open_lots: list[Lot]
    sell_qty: Decimal
    sell_price: Decimal
    sell_fee: Decimal
    sell_tax: Decimal = Decimal("0")


@dataclass
class BuyResult:
    """Result of `apply_buy` — the newly created lot."""

    new_lot: Lot


@dataclass
class SellResult:
    """Result of `apply_sell` — realized P&L + updated lots."""

    realized_pnl: Decimal
    updated_lots: list[Lot]
    qty_consumed: Decimal


def apply_buy(
    lot_id: int, qty: Decimal, price: Decimal, fee: Decimal
) -> BuyResult:
    """Create a new FIFO lot for a BUY trade.

    Delegates to `FIFOEngine.make_lot`. Buy-side fee is embedded in
    `cost_per_unit`. Sell-side fee/tax is handled later in `apply_sell`.

    Raises:
        ValueError: when `qty <= 0` (per FIFOEngine.make_lot).
    """
    lot = FIFOEngine.make_lot(lot_id=lot_id, qty=qty, price=price, fee=fee)
    return BuyResult(new_lot=lot)


def apply_sell(inputs: CostBasisInputs) -> SellResult:
    """Consume open lots FIFO-order, compute realized P&L.

    Wraps `FIFOEngine(open_lots).process_sell(...)`. Returned `updated_lots`
    is a fresh list — caller may mutate freely.

    Raises:
        InsufficientSharesError: when `sell_qty` exceeds available lots.
    """
    engine = FIFOEngine(open_lots=inputs.open_lots)
    result: FIFOResult = engine.process_sell(
        qty=inputs.sell_qty,
        price=inputs.sell_price,
        fee=inputs.sell_fee,
        tax=inputs.sell_tax,
    )
    return SellResult(
        realized_pnl=result.realized_pnl,
        updated_lots=result.updated_lots,
        qty_consumed=result.qty_consumed,
    )


def average_cost(lots: list[Lot]) -> Decimal:
    """Weighted average cost across open (non-exhausted) lots.

    avg = Σ(remaining_qty × cost_per_unit) / Σ(remaining_qty)

    Returns `Decimal("0")` when total remaining qty is zero
    (empty list, all exhausted, or all zero remaining).
    """
    total_qty = Decimal("0")
    total_cost = Decimal("0")
    for lot in lots:
        if lot.remaining_qty <= Decimal("0"):
            continue
        total_qty += lot.remaining_qty
        total_cost += lot.remaining_qty * lot.cost_per_unit
    if total_qty <= Decimal("0"):
        return Decimal("0")
    return total_cost / total_qty
