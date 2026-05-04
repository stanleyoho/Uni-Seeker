"""Pure FIFO engine — no database, no side effects."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal


class InsufficientSharesError(ValueError):
    """Raised when a SELL quantity exceeds available open lots."""


@dataclass
class Lot:
    lot_id: int
    original_qty: Decimal
    remaining_qty: Decimal
    cost_per_unit: Decimal
    is_exhausted: bool = False


@dataclass
class FIFOResult:
    realized_pnl: Decimal
    updated_lots: list[Lot]
    qty_consumed: Decimal


class FIFOEngine:
    """Stateful FIFO engine. open_lots must be sorted by lot_id ASC (oldest first)."""

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
        cost_per_unit = (price * qty + fee) / qty
        return Lot(lot_id=lot_id, original_qty=qty, remaining_qty=qty, cost_per_unit=cost_per_unit)

    def process_sell(self, qty: Decimal, price: Decimal, fee: Decimal, tax: Decimal) -> FIFOResult:
        available = sum(lot.remaining_qty for lot in self._lots)
        if available < qty:
            raise InsufficientSharesError(f"Cannot sell {qty}: only {available} shares available.")

        proceeds = price * qty - fee - tax
        remaining_to_sell = qty
        total_cost = Decimal("0")
        touched_lots: list[Lot] = []

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
            touched_lots.append(lot)

        return FIFOResult(realized_pnl=proceeds - total_cost, updated_lots=list(self._lots), qty_consumed=qty)

    def process_split(self, ratio: Decimal) -> list[Lot]:
        for lot in self._lots:
            lot.remaining_qty = lot.remaining_qty * ratio
            lot.original_qty = lot.original_qty * ratio
            lot.cost_per_unit = lot.cost_per_unit / ratio
        return list(self._lots)
