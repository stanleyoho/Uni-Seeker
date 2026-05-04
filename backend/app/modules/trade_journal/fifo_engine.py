"""Pure FIFO engine — no database, no side effects."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal


class InsufficientSharesError(ValueError):
    """Raised when a SELL quantity exceeds available open lots."""


@dataclass
class Lot:
    """One BUY batch. Corresponds to one trade_lots row."""

    lot_id: int
    original_qty: Decimal
    remaining_qty: Decimal
    cost_per_unit: Decimal
    is_exhausted: bool = False


@dataclass
class FIFOResult:
    """Result of process_sell()."""

    realized_pnl: Decimal
    updated_lots: list[Lot]
    qty_consumed: Decimal


class FIFOEngine:
    """Stateful FIFO engine. Stateful within a single call chain; instantiate once per trade operation.
    open_lots must be sorted by lot_id ASC (oldest first).
    """

    def __init__(self, open_lots: list[Lot]) -> None:
        self._lots: list[Lot] = [
            Lot(
                lot_id=lot.lot_id,
                original_qty=lot.original_qty,
                remaining_qty=lot.remaining_qty,
                cost_per_unit=lot.cost_per_unit,
                is_exhausted=lot.is_exhausted,
            )
            for lot in open_lots
        ]

    @staticmethod
    def make_lot(lot_id: int, qty: Decimal, price: Decimal, fee: Decimal) -> Lot:
        if qty <= Decimal("0"):
            raise ValueError(f"BUY quantity must be positive, got {qty}")
        cost_per_unit = (price * qty + fee) / qty
        return Lot(lot_id=lot_id, original_qty=qty, remaining_qty=qty, cost_per_unit=cost_per_unit)

    def process_sell(self, qty: Decimal, price: Decimal, fee: Decimal, tax: Decimal) -> FIFOResult:
        """Consume open lots in FIFO order, compute realized P&L.

        realized_pnl = proceeds - cost
        proceeds = price * qty - fee - tax
        cost = sum(cost_per_unit * shares_consumed) for each touched lot

        Note: Buy-side fee is embedded in cost_per_unit (via make_lot).
        Sell-side fee and tax reduce proceeds.

        WARNING: Returned Lot objects in updated_lots are live references to internal state.
        Callers must not mutate them.
        """
        available = sum((lot.remaining_qty for lot in self._lots), Decimal("0"))
        if available < qty:
            raise InsufficientSharesError(f"Cannot sell {qty}: only {available} shares available.")

        proceeds = price * qty - fee - tax
        remaining_to_sell = qty
        total_cost = Decimal("0")

        for lot in self._lots:
            if remaining_to_sell <= Decimal("0"):
                break
            if lot.remaining_qty <= Decimal("0"):
                continue
            consume = min(lot.remaining_qty, remaining_to_sell)
            total_cost += lot.cost_per_unit * consume
            lot.remaining_qty -= consume
            remaining_to_sell -= consume
            if lot.remaining_qty == Decimal("0"):
                lot.is_exhausted = True

        # Return all lots (not just consumed ones) so callers can access untouched lots
        # by index — e.g. position_sync needs to check is_exhausted on every lot.
        return FIFOResult(realized_pnl=proceeds - total_cost, updated_lots=list(self._lots), qty_consumed=qty)

    def process_split(self, ratio: Decimal) -> list[Lot]:
        """Apply a stock split ratio to all open lots.

        WARNING: Returned Lot objects are live references to internal state.
        Callers must not mutate them after calling this method.
        """
        for lot in self._lots:
            lot.remaining_qty = lot.remaining_qty * ratio
            lot.original_qty = lot.original_qty * ratio
            lot.cost_per_unit = lot.cost_per_unit / ratio
        return list(self._lots)
