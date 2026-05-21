"""Portfolio dividend processor — pure functions, Decimal throughout.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.1 / §7.

Two dividend types, distinct effects on portfolio state:

- **CASH dividend** (現金股利): does NOT touch lots / qty.
  Computes net cash received and the corresponding realized P&L delta. Caller
  (service layer) is responsible for persisting cash income and incrementing
  `positions.realized_pnl`.

- **STOCK dividend** (股票股利 / 配股): adjusts every open lot in place by the
  same ratio. Per-lot invariant preserved: `old_qty * old_cost == new_qty *
  new_cost`. Conceptually a stock-split for cost basis purposes (spec §5.1
  describes stock dividend as "視同 split"). True corporate splits are
  handled by a separate processor in Phase 4+ — this module covers
  dividend-shaped ratios only.

**Anti-coupling invariant** (spec §11.2): no SQLAlchemy ORM imports, no
FastAPI imports. `Lot` is re-exported from `cost_basis`, which itself
re-exports it from `trade_journal.fifo_engine` — this stays purely within
the domain layer (no schema coupling).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.portfolio.cost_basis import Lot

__all__ = [
    "CashDividendInputs",
    "CashDividendResult",
    "StockDividendInputs",
    "StockDividendResult",
    "process_cash_dividend",
    "process_stock_dividend",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass(frozen=True)
class CashDividendInputs:
    """Inputs for a cash dividend event.

    - `qty_at_record`: shares held at the dividend record date.
    - `amount_per_share`: gross dividend per share (currency-agnostic).
    - `withholding_tax`: total tax withheld at source. Must be `<= total_amount`.
    """

    qty_at_record: Decimal
    amount_per_share: Decimal
    withholding_tax: Decimal = Decimal("0")


@dataclass(frozen=True)
class CashDividendResult:
    """Result of a cash dividend computation.

    - `total_amount`: gross = `qty_at_record * amount_per_share`.
    - `net_amount`: net = `total_amount - withholding_tax`.
    - `realized_pnl_delta`: amount to add to `positions.realized_pnl`. Equals
      `net_amount` by current design (spec §7.2 treats cash dividend as a
      realized cash gain). Service layer decides whether to also persist
      a `portfolio_dividends` row separately.
    """

    total_amount: Decimal
    net_amount: Decimal
    realized_pnl_delta: Decimal


@dataclass(frozen=True)
class StockDividendInputs:
    """Inputs for a stock dividend (配股) event.

    - `ratio`: new shares per existing share, e.g. `Decimal("0.1")` means
      every 10 shares earn 1 extra share. Must be `>= 0`. Negative values
      are rejected — reverse splits live in a future `split_processor`.
    - `open_lots`: snapshot of open lots at record date. Caller passes
      a fresh list; `process_stock_dividend` does NOT mutate it.
    """

    ratio: Decimal
    open_lots: list[Lot]


@dataclass(frozen=True)
class StockDividendResult:
    """Result of a stock dividend adjustment.

    - `updated_lots`: NEW `Lot` instances with adjusted `remaining_qty`,
      `original_qty`, and `cost_per_unit`. Original list left untouched.
    - `total_new_qty_added`: Σ (lot.remaining_qty * ratio) across all
      lots — useful for audit logging / journal `quantity` field.
    """

    updated_lots: list[Lot]
    total_new_qty_added: Decimal


def process_cash_dividend(inputs: CashDividendInputs) -> CashDividendResult:
    """Compute a cash dividend result. No side effects.

    Formula:
        total_amount       = qty_at_record * amount_per_share
        net_amount         = total_amount - withholding_tax
        realized_pnl_delta = net_amount

    Raises:
        ValueError: when any input is negative, or when `withholding_tax`
            exceeds `total_amount` (would produce negative net — spec is
            silent on refund semantics, so we surface the anomaly upward).
    """
    if inputs.qty_at_record < _ZERO:
        raise ValueError(
            f"qty_at_record must be non-negative, got {inputs.qty_at_record}"
        )
    if inputs.amount_per_share < _ZERO:
        raise ValueError(
            f"amount_per_share must be non-negative, got {inputs.amount_per_share}"
        )
    if inputs.withholding_tax < _ZERO:
        raise ValueError(
            f"withholding_tax must be non-negative, got {inputs.withholding_tax}"
        )

    total_amount = inputs.qty_at_record * inputs.amount_per_share

    if inputs.withholding_tax > total_amount:
        raise ValueError(
            f"withholding_tax ({inputs.withholding_tax}) exceeds "
            f"total_amount ({total_amount}); refund scenarios are not supported"
        )

    net_amount = total_amount - inputs.withholding_tax
    return CashDividendResult(
        total_amount=total_amount,
        net_amount=net_amount,
        realized_pnl_delta=net_amount,
    )


def process_stock_dividend(inputs: StockDividendInputs) -> StockDividendResult:
    """Scale every open lot by `(1 + ratio)`, preserving per-lot total cost.

    For each lot:
        scale             = 1 + ratio
        new_remaining_qty = old_remaining_qty * scale
        new_original_qty  = old_original_qty  * scale
        new_cost_per_unit = old_cost_per_unit / scale

    Invariant per lot: `old_remaining_qty * old_cost_per_unit
                       == new_remaining_qty * new_cost_per_unit`.

    Edge cases:
        - `ratio == 0`        → no-op; returns fresh Lot copies, `total_new_qty_added = 0`.
        - `open_lots == []`   → returns empty list, `total_new_qty_added = 0`.
        - exhausted lots       (`remaining_qty == 0`) are still copied through
          unchanged — their `is_exhausted` flag is preserved.

    Raises:
        ValueError: when `ratio < 0` (reverse splits belong in a separate
            split_processor; not a dividend operation).
    """
    if inputs.ratio < _ZERO:
        raise ValueError(
            f"ratio must be non-negative for stock dividend, got {inputs.ratio}; "
            "use split_processor for reverse splits"
        )

    scale = _ONE + inputs.ratio
    total_new_qty_added = _ZERO
    updated_lots: list[Lot] = []

    for lot in inputs.open_lots:
        if scale == _ONE:
            # ratio == 0 — copy through unchanged
            updated_lots.append(
                Lot(
                    lot_id=lot.lot_id,
                    original_qty=lot.original_qty,
                    remaining_qty=lot.remaining_qty,
                    cost_per_unit=lot.cost_per_unit,
                    is_exhausted=lot.is_exhausted,
                )
            )
            continue

        new_remaining = lot.remaining_qty * scale
        new_original = lot.original_qty * scale
        # Division — Decimal-aware, no float. Keeps full precision.
        new_cost_per_unit = lot.cost_per_unit / scale

        total_new_qty_added += lot.remaining_qty * inputs.ratio

        updated_lots.append(
            Lot(
                lot_id=lot.lot_id,
                original_qty=new_original,
                remaining_qty=new_remaining,
                cost_per_unit=new_cost_per_unit,
                is_exhausted=lot.is_exhausted,
            )
        )

    return StockDividendResult(
        updated_lots=updated_lots,
        total_new_qty_added=total_new_qty_added,
    )
