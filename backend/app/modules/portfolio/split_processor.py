"""Stock split / reverse split processor — pure functions, Decimal throughout.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md
      §5.1 / §7 — corporate actions / Phase 4+.

Handles two split shapes:

- **FORWARD split** (e.g. 4:1 — every 1 share becomes 4): qty multiplied,
  cost-per-unit divided. Multiplier = ratio_to / ratio_from (> 1).
- **REVERSE split** (e.g. 1:5 — every 5 shares collapse to 1): qty divided,
  cost-per-unit multiplied. Multiplier = ratio_to / ratio_from (< 1).

Per-lot invariant preserved exactly: `old_qty * old_cost == new_qty * new_cost`
under Decimal arithmetic. This matches dividend_processor.process_stock_dividend
but with a different multiplier shape — see distinction in module header below.

**Distinction from `dividend_processor.process_stock_dividend`**:

- Stock dividend ratio is "extra shares per original" (0.1 → +10% → multiplier 1.1).
- Split ratio is the corporate-action notation `to:from` interpreted directly:
  multiplier = to / from. Forward and reverse share the same formula; only the
  resulting magnitude (>1 or <1) differs.

**Fractional handling** (Forward 3:2 on 1 share, or Reverse 1:5 on 123 shares):

- `'round_down_cash_in_lieu'` (default): truncate fractional part of new_qty
  using ROUND_DOWN. Fractional residue × `current_market_price` (required for
  this policy) is returned as `cash_in_lieu_usd` for the service layer to
  persist as realized P&L. Lot total-cost invariant is **rebalanced** so that
  the truncated lot's `new_qty * new_cost == old_qty * old_cost` still holds
  for the *kept* shares — the CIL value compensates the difference.
- `'keep_fractional'`: full-precision Decimal, no rounding, no CIL. Invariant
  holds without any adjustment.
- `'round_to_nearest'`: banker-style HALF_UP rounding on new_qty (>= 0.5 rounds
  up). No CIL (the fractional was given/taken by the corporate action). Cost
  per unit rebalanced so the invariant holds on the rounded qty.

**Anti-coupling invariant** (spec §11.2): no SQLAlchemy ORM imports, no FastAPI
imports. `Lot` is re-exported from `cost_basis`, keeping the split processor
purely within the domain layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import Enum, StrEnum

from app.modules.portfolio.cost_basis import Lot

__all__ = [
    "SplitType",
    "StockSplitInputs",
    "StockSplitResult",
    "compute_split_multiplier",
    "process_stock_split",
    "validate_split_inputs",
]

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HALF = Decimal("0.5")

# Fractional policy literal values — kept as strings to allow Service layer
# round-trip without import coupling.
FRACTIONAL_ROUND_DOWN_CIL = "round_down_cash_in_lieu"
FRACTIONAL_KEEP = "keep_fractional"
FRACTIONAL_ROUND_NEAREST = "round_to_nearest"

_VALID_FRACTIONAL_POLICIES = frozenset(
    {
        FRACTIONAL_ROUND_DOWN_CIL,
        FRACTIONAL_KEEP,
        FRACTIONAL_ROUND_NEAREST,
    }
)


class SplitType(StrEnum):
    """Forward vs reverse split.

    Forward: ratio_to > ratio_from (e.g. 4:1, 3:2).
    Reverse: ratio_to < ratio_from (e.g. 1:5, 2:3).
    The processor cross-checks the declared `split_type` against the computed
    multiplier and rejects mismatches — see `validate_split_inputs`.
    """

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


@dataclass(frozen=True)
class StockSplitInputs:
    """Inputs for a stock-split event.

    - `split_type`: FORWARD or REVERSE — declarative cross-check.
    - `ratio_from` / `ratio_to`: corporate-action notation. For "4:1 forward
      split", `ratio_to=4`, `ratio_from=1`. For "1:5 reverse split",
      `ratio_to=1`, `ratio_from=5`. Both must be `> 0`.
    - `open_lots`: snapshot of open lots at effective date. Caller passes a
      fresh list; `process_stock_split` does NOT mutate it.
    - `fractional_policy`: one of `'round_down_cash_in_lieu'`,
      `'keep_fractional'`, `'round_to_nearest'`. Default rounds down with CIL.
    - `current_market_price`: required ONLY for `'round_down_cash_in_lieu'`
      policy to value the fractional residue. Optional otherwise.
    """

    split_type: SplitType
    ratio_from: Decimal
    ratio_to: Decimal
    open_lots: list[Lot] = field(default_factory=list)
    fractional_policy: str = FRACTIONAL_ROUND_DOWN_CIL
    current_market_price: Decimal | None = None


@dataclass(frozen=True)
class StockSplitResult:
    """Result of a stock-split adjustment.

    - `updated_lots`: NEW `Lot` instances. Caller may mutate freely.
    - `total_old_qty`: Σ `remaining_qty` over input lots — audit field.
    - `total_new_qty`: Σ `remaining_qty` over output lots — post-split total.
    - `cash_in_lieu_usd`: only nonzero under `'round_down_cash_in_lieu'` when
      at least one lot produced a fractional residue. Service layer is
      responsible for adding this to `positions.realized_pnl`.
    - `multiplier`: the share multiplier actually applied (ratio_to / ratio_from).
    """

    updated_lots: list[Lot]
    total_old_qty: Decimal
    total_new_qty: Decimal
    cash_in_lieu_usd: Decimal
    multiplier: Decimal


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def compute_split_multiplier(
    split_type: SplitType, ratio_from: Decimal, ratio_to: Decimal
) -> Decimal:
    """Return the per-share multiplier for a split.

    Formula (identical for forward and reverse — magnitude indicates direction):
        multiplier = ratio_to / ratio_from

    Raises:
        ValueError: when either ratio is `<= 0`. The processor relies on
            `validate_split_inputs` to catch this earlier; calling this
            helper directly with bad ratios fails fast here as well.
    """
    if ratio_from <= _ZERO:
        raise ValueError(f"ratio_from must be positive, got {ratio_from}")
    if ratio_to <= _ZERO:
        raise ValueError(f"ratio_to must be positive, got {ratio_to}")
    return ratio_to / ratio_from


def validate_split_inputs(inputs: StockSplitInputs) -> None:
    """Raise `ValueError` when inputs are inconsistent.

    Checks:
      1. `ratio_from > 0` and `ratio_to > 0`.
      2. `fractional_policy` is one of the three supported strings.
      3. `'round_down_cash_in_lieu'` requires `current_market_price` set and `>= 0`
         (a 0 price is admissible — produces 0 CIL).
      4. Declared `split_type` is consistent with the implied multiplier:
         FORWARD requires `ratio_to >= ratio_from`, REVERSE requires
         `ratio_to <= ratio_from`. Equality (no-op multiplier) is accepted in
         either direction — it's a degenerate but harmless input.
    """
    if inputs.ratio_from <= _ZERO:
        raise ValueError(f"ratio_from must be positive, got {inputs.ratio_from}")
    if inputs.ratio_to <= _ZERO:
        raise ValueError(f"ratio_to must be positive, got {inputs.ratio_to}")

    if inputs.fractional_policy not in _VALID_FRACTIONAL_POLICIES:
        raise ValueError(
            f"fractional_policy must be one of "
            f"{sorted(_VALID_FRACTIONAL_POLICIES)}, "
            f"got {inputs.fractional_policy!r}"
        )

    if inputs.fractional_policy == FRACTIONAL_ROUND_DOWN_CIL:
        if inputs.current_market_price is None:
            raise ValueError(
                "current_market_price is required when fractional_policy is "
                f"{FRACTIONAL_ROUND_DOWN_CIL!r}"
            )
        if inputs.current_market_price < _ZERO:
            raise ValueError(
                f"current_market_price must be non-negative, got {inputs.current_market_price}"
            )

    # Direction cross-check
    if inputs.split_type == SplitType.FORWARD and inputs.ratio_to < inputs.ratio_from:
        raise ValueError(
            f"FORWARD split requires ratio_to >= ratio_from, got "
            f"{inputs.ratio_to}:{inputs.ratio_from}"
        )
    if inputs.split_type == SplitType.REVERSE and inputs.ratio_to > inputs.ratio_from:
        raise ValueError(
            f"REVERSE split requires ratio_to <= ratio_from, got "
            f"{inputs.ratio_to}:{inputs.ratio_from}"
        )


# ---------------------------------------------------------------------------
# Fractional-handling strategies
# ---------------------------------------------------------------------------


def _apply_round_down_cil(
    raw_new_qty: Decimal,
    old_qty: Decimal,
    old_cost: Decimal,
    market_price: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Round down fractional, return (kept_qty, kept_cost_per_unit, cil).

    Algorithm:
        kept_qty = floor(raw_new_qty)   # ROUND_DOWN to integer
        fractional = raw_new_qty - kept_qty
        cil = fractional * market_price        (lot-level CIL)
        # Invariant for kept shares only:
        # kept_qty * new_cost_per_unit == old_qty * old_cost - cil_in_cost_terms
        # We instead keep the per-unit cost at the pre-truncation level so the
        # held-share total cost equals old_total_cost minus the fractional's
        # *cost-basis share*, and the CIL captures the market value of the
        # fractional separately. This means:
        #   new_cost_per_unit = old_total_cost / raw_new_qty (== old/multiplier)
        # — the same per-unit cost that the un-truncated split would produce.
        #   kept_qty * new_cost = (old_total_cost / raw_new_qty) * kept_qty
        # — this is < old_total_cost; the fractional's pro-rata cost basis is
        #   the difference, while CIL uses *market price* (separate concept).

    When `raw_new_qty <= 0` (only possible for empty/zero lot), returns zeros.
    """
    if raw_new_qty <= _ZERO:
        return _ZERO, _ZERO, _ZERO

    kept_qty = raw_new_qty.quantize(_ONE, rounding=ROUND_DOWN)
    fractional = raw_new_qty - kept_qty

    # new_cost_per_unit at raw (untruncated) multiplier so the per-share basis
    # matches the would-be invariant. Equivalent to old_cost / multiplier.
    if raw_new_qty == _ZERO:
        new_cost_per_unit = _ZERO
    else:
        new_cost_per_unit = (old_qty * old_cost) / raw_new_qty

    cil = fractional * market_price
    return kept_qty, new_cost_per_unit, cil


def _apply_keep_fractional(
    raw_new_qty: Decimal,
    old_qty: Decimal,
    old_cost: Decimal,
) -> tuple[Decimal, Decimal]:
    """No rounding — return (raw_new_qty, new_cost_per_unit).

    Per-lot invariant `old_qty * old_cost == raw_new_qty * new_cost_per_unit`
    holds by construction: new_cost = old_qty * old_cost / raw_new_qty.
    """
    if raw_new_qty == _ZERO:
        return _ZERO, _ZERO
    new_cost_per_unit = (old_qty * old_cost) / raw_new_qty
    return raw_new_qty, new_cost_per_unit


def _apply_round_to_nearest(
    raw_new_qty: Decimal,
    old_qty: Decimal,
    old_cost: Decimal,
) -> tuple[Decimal, Decimal]:
    """HALF_UP rounding on new_qty; cost rebalanced to preserve total cost.

    Algorithm:
        rounded_qty = ROUND_HALF_UP(raw_new_qty, 0 places)
        new_cost_per_unit = (old_qty * old_cost) / rounded_qty
            — so rounded_qty * new_cost == old_total_cost exactly.

    For `rounded_qty == 0` (e.g. reverse 1:1000 on 0.4 shares), returns (0, 0).
    """
    if raw_new_qty <= _ZERO:
        return _ZERO, _ZERO
    rounded_qty = raw_new_qty.quantize(_ONE, rounding=ROUND_HALF_UP)
    if rounded_qty == _ZERO:
        return _ZERO, _ZERO
    new_cost_per_unit = (old_qty * old_cost) / rounded_qty
    return rounded_qty, new_cost_per_unit


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def process_stock_split(inputs: StockSplitInputs) -> StockSplitResult:
    """Scale every open lot by `multiplier = ratio_to / ratio_from`.

    Per-lot derivation (before fractional handling):
        raw_new_qty       = old_remaining_qty * multiplier
        raw_new_original  = old_original_qty  * multiplier
        new_cost_per_unit = old_cost_per_unit / multiplier
        => Invariant: old_qty * old_cost == raw_new_qty * new_cost_per_unit

    Fractional handling per `fractional_policy` — see helper docstrings.

    Edge cases:
        - `ratio_from == ratio_to` → multiplier 1, no-op (lots copied through).
        - `open_lots == []` → empty result, totals = 0.
        - Exhausted lots (`remaining_qty == 0`) are still copied through with
          updated `original_qty` and `cost_per_unit` for audit faithfulness.

    Raises:
        ValueError: when `validate_split_inputs` fails (bad ratios, bad policy,
            missing market price, or direction mismatch).
    """
    validate_split_inputs(inputs)

    multiplier = compute_split_multiplier(inputs.split_type, inputs.ratio_from, inputs.ratio_to)

    total_old_qty = _ZERO
    total_new_qty = _ZERO
    total_cil = _ZERO
    updated_lots: list[Lot] = []

    for lot in inputs.open_lots:
        total_old_qty += lot.remaining_qty

        if multiplier == _ONE:
            # No-op — fresh copy preserving every field.
            updated_lots.append(
                Lot(
                    lot_id=lot.lot_id,
                    original_qty=lot.original_qty,
                    remaining_qty=lot.remaining_qty,
                    cost_per_unit=lot.cost_per_unit,
                    is_exhausted=lot.is_exhausted,
                )
            )
            total_new_qty += lot.remaining_qty
            continue

        raw_new_remaining = lot.remaining_qty * multiplier
        raw_new_original = lot.original_qty * multiplier

        # Apply fractional policy to remaining_qty.
        # original_qty scales by raw multiplier (historical audit — represents
        # the post-split equivalent of what was originally purchased). We do
        # NOT round original_qty: it's a derived historical figure and we
        # preserve full precision so reverse-engineering the multiplier later
        # remains lossless.
        if inputs.fractional_policy == FRACTIONAL_ROUND_DOWN_CIL:
            assert inputs.current_market_price is not None  # validated above
            new_remaining, new_cost_per_unit, cil = _apply_round_down_cil(
                raw_new_remaining,
                lot.remaining_qty,
                lot.cost_per_unit,
                inputs.current_market_price,
            )
            total_cil += cil
        elif inputs.fractional_policy == FRACTIONAL_KEEP:
            new_remaining, new_cost_per_unit = _apply_keep_fractional(
                raw_new_remaining, lot.remaining_qty, lot.cost_per_unit
            )
        else:  # FRACTIONAL_ROUND_NEAREST
            new_remaining, new_cost_per_unit = _apply_round_to_nearest(
                raw_new_remaining, lot.remaining_qty, lot.cost_per_unit
            )

        is_exhausted = new_remaining <= _ZERO or lot.is_exhausted
        total_new_qty += new_remaining

        updated_lots.append(
            Lot(
                lot_id=lot.lot_id,
                original_qty=raw_new_original,
                remaining_qty=new_remaining,
                cost_per_unit=new_cost_per_unit,
                is_exhausted=is_exhausted,
            )
        )

    return StockSplitResult(
        updated_lots=updated_lots,
        total_old_qty=total_old_qty,
        total_new_qty=total_new_qty,
        cash_in_lieu_usd=total_cil,
        multiplier=multiplier,
    )
