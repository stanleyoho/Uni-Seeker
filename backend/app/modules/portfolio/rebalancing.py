"""Portfolio rebalancing — pure module.

Spec: Portfolio Phase 5+ Pro-tier rebalancing tool. Given the user's
current open positions and a target allocation (% per symbol), compute
the trades required to reach the target. **No DB, no API, Decimal only.**

Algorithm:
  1. ``total_value = Σ(qty × last_price)`` across current positions.
  2. For each ``TargetAllocation``:
       target_value  = total_value × target_pct / 100
       current_value = qty × last_price (0 if symbol absent from current)
       delta_value   = target_value - current_value
       delta_qty     = delta_value / last_price
     -  delta_value >  0 → BUY  ``delta_qty``  shares
     -  delta_value <  0 → SELL ``|delta_qty|`` shares
     -  ``|delta_value| < min_trade_value`` → SKIP (no trade)
  3. Any symbol present in current but absent from target → full SELL.
  4. ``cash_residual`` = total_value − Σ(target_value of traded symbols)
     (i.e. rounding / skipped-trade slack returned to the user as cash).

Validation:
  - ``sum(target_pct)`` must equal 100 within Decimal tolerance (``0.01``).
  - ``target_pct`` must be ≥ 0.
  - Each ``(symbol, market)`` in ``targets`` must be unique.

Edge cases (deliberate, documented):
  - **Symbol in target, absent from current** → full BUY (delta = target).
  - **Symbol in current, absent from target** → full SELL (current → 0).
  - **Total portfolio value == 0** → no BUYs possible; all targets become
    skipped. Returns an empty trade list with zero cash residual.
  - **last_price == 0** for a current position → treated as zero current
    value; cannot derive a BUY qty for that symbol (price-less BUY would
    division-by-zero), so such a target is **skipped** with a rationale
    rather than raising. We never let bad price data crash the planner.
  - **min_trade_value == 0** → no skipping; every non-zero delta becomes
    a trade (useful for tests and "exact" rebalancing modes).

User-controllable knobs:
  - ``min_trade_value`` (default 100 in the position's currency) — guards
    against churn from cents-of-drift; users tolerating more drift can
    raise it.
  - ``rebalance_mode`` is **percentage** only in Phase 1. The dataclass
    surface keeps room for a future "absolute" mode but the function
    signature does not yet expose it (premature parametrisation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

__all__ = [
    "CurrentPosition",
    "TargetAllocation",
    "SuggestedTrade",
    "RebalanceResult",
    "compute_rebalance",
    "validate_targets",
]


_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_PCT_TOLERANCE = Decimal("0.01")  # sum(target_pct) must be within ±0.01 of 100


@dataclass(frozen=True)
class CurrentPosition:
    """One row of the user's current open portfolio.

    ``current_value`` is precomputed by the caller (service layer) from
    ``qty × last_price`` so the pure module doesn't have to assume the
    multiplication semantics for fractional shares, splits, etc.
    """

    symbol: str
    market: str
    qty: Decimal
    last_price: Decimal
    current_value: Decimal


@dataclass(frozen=True)
class TargetAllocation:
    """A target weight for one (symbol, market) tuple. ``target_pct`` is
    a number in [0, 100]; the caller passes Decimal to preserve precision."""

    symbol: str
    market: str
    target_pct: Decimal


@dataclass(frozen=True)
class SuggestedTrade:
    """A single proposed trade to move the portfolio toward target."""

    symbol: str
    market: str
    action: Literal["BUY", "SELL"]
    qty: Decimal
    estimated_price: Decimal
    estimated_value: Decimal
    rationale: str  # human-readable, surfaced to the UI as a tooltip


@dataclass(frozen=True)
class RebalanceResult:
    """Output of :func:`compute_rebalance`.

    - ``total_portfolio_value``: snapshot used for the math; lets the API
      layer echo it back so the UI can show "based on $X portfolio value".
    - ``suggested_trades``: list of BUY/SELL trades the user should make.
    - ``final_allocation_pct``: per ``"{symbol}|{market}"`` key, the
      expected allocation percentage AFTER the suggested trades execute.
      Useful for an after-state pie chart.
    - ``skipped_trades``: trades dropped due to ``min_trade_value``. Each
      entry carries enough info for the UI to explain the skip.
    - ``cash_residual``: value not allocated to any trade (rounding /
      skipped slack). Positive means the user has unallocated cash.
    """

    total_portfolio_value: Decimal
    suggested_trades: list[SuggestedTrade]
    final_allocation_pct: dict[str, Decimal]
    skipped_trades: list[dict] = field(default_factory=list)
    cash_residual: Decimal = _ZERO


# ── validation ─────────────────────────────────────────────────────────────


def validate_targets(targets: list[TargetAllocation]) -> None:
    """Raise ``ValueError`` if the target list is unusable.

    Three failure modes:
      1. **Duplicate (symbol, market) key** — ambiguous target weight.
      2. **Negative ``target_pct``** — nonsensical allocation.
      3. **Sum of percentages ≠ 100** (within ±0.01 tolerance) — Phase 1
         requires the user to fully partition the portfolio. Future
         "partial rebalance" mode would relax this, but explicit is
         better than implicit-with-residual.

    An empty list does NOT raise — empty targets is a legitimate signal
    meaning "exit all positions" (every current symbol → full SELL).
    """
    if not targets:
        # Empty is allowed: caller wants to exit everything.
        return

    # Negatives first (cheap, clear error message).
    for t in targets:
        if t.target_pct < _ZERO:
            raise ValueError(
                f"target_pct must be ≥ 0, got {t.target_pct} for "
                f"{t.symbol}/{t.market}"
            )

    # Duplicate detection on the composite key (symbol, market) — same
    # symbol on TWSE vs OTC is a different holding, so we key on both.
    seen: set[tuple[str, str]] = set()
    for t in targets:
        key = (t.symbol, t.market)
        if key in seen:
            raise ValueError(
                f"duplicate target for {t.symbol}/{t.market}"
            )
        seen.add(key)

    total = sum((t.target_pct for t in targets), _ZERO)
    if abs(total - _HUNDRED) > _PCT_TOLERANCE:
        raise ValueError(
            f"sum(target_pct) must equal 100 (±{_PCT_TOLERANCE}); got {total}"
        )


# ── core computation ───────────────────────────────────────────────────────


def _key(symbol: str, market: str) -> str:
    """Stable composite key for dict lookups. Used in the public
    ``final_allocation_pct`` dict too, so the format is API-visible."""
    return f"{symbol}|{market}"


def compute_rebalance(
    positions: list[CurrentPosition],
    targets: list[TargetAllocation],
    min_trade_value: Decimal = Decimal("100"),
) -> RebalanceResult:
    """Compute trades to move ``positions`` toward ``targets``.

    See module docstring for the algorithm + edge case contract.

    Args:
        positions: current open positions (qty > 0). Closed positions
            should already have been filtered by the caller.
        targets: desired allocation percentages summing to 100.
        min_trade_value: ``|delta_value|`` below this is skipped.
            Defaults to 100 (in the position's currency unit). Must be ≥ 0.

    Returns:
        ``RebalanceResult`` with suggested trades, skips, and after-state.

    Raises:
        ValueError: when ``min_trade_value`` is negative or any of
            ``validate_targets``'s rules fire.
    """
    if min_trade_value < _ZERO:
        raise ValueError(
            f"min_trade_value must be ≥ 0, got {min_trade_value}"
        )

    validate_targets(targets)

    # Pre-aggregate positions into a lookup. We accept the input order as
    # canonical so the resulting trade list can preserve user intent.
    pos_by_key: dict[str, CurrentPosition] = {
        _key(p.symbol, p.market): p for p in positions
    }

    total_value = sum((p.current_value for p in positions), _ZERO)

    suggested: list[SuggestedTrade] = []
    skipped: list[dict] = []
    # Track which keys had a non-skipped trade so we can compute
    # final_allocation_pct based on what the user is actually committing to.
    committed_value: dict[str, Decimal] = {}

    # ---- pass 1: walk every target ---------------------------------------
    for t in targets:
        k = _key(t.symbol, t.market)
        target_value = total_value * t.target_pct / _HUNDRED
        current = pos_by_key.get(k)
        current_value = current.current_value if current is not None else _ZERO
        delta_value = target_value - current_value

        # The target may be brand-new (no current row). For BUYs we need a
        # price to convert delta_value → delta_qty. Without one we can't
        # propose anything sensible; flag as skip with rationale.
        ref_price = current.last_price if current is not None else _ZERO

        if abs(delta_value) < min_trade_value:
            # Below the min-trade threshold → skip but still credit the
            # symbol's CURRENT value to committed_value so final
            # allocation reflects "we left this one alone".
            skipped.append(
                {
                    "symbol": t.symbol,
                    "market": t.market,
                    "target_pct": str(t.target_pct),
                    "delta_value": str(delta_value),
                    "reason": "below_min_trade_value",
                }
            )
            committed_value[k] = current_value
            continue

        if delta_value > _ZERO:
            # BUY path needs a price. Use ref_price; if zero, skip.
            if ref_price <= _ZERO:
                skipped.append(
                    {
                        "symbol": t.symbol,
                        "market": t.market,
                        "target_pct": str(t.target_pct),
                        "delta_value": str(delta_value),
                        "reason": "missing_price_for_buy",
                    }
                )
                committed_value[k] = current_value
                continue
            qty = delta_value / ref_price
            suggested.append(
                SuggestedTrade(
                    symbol=t.symbol,
                    market=t.market,
                    action="BUY",
                    qty=qty,
                    estimated_price=ref_price,
                    estimated_value=delta_value,
                    rationale=(
                        f"current {_pct_of(current_value, total_value)}% → "
                        f"target {t.target_pct}% (buy to add "
                        f"{_fmt_money(delta_value)})"
                    ),
                )
            )
            committed_value[k] = target_value
        else:
            # SELL path: delta_value < 0; sell_value = -delta_value > 0.
            if ref_price <= _ZERO:
                # Cannot quote a SELL price; defensively skip.
                skipped.append(
                    {
                        "symbol": t.symbol,
                        "market": t.market,
                        "target_pct": str(t.target_pct),
                        "delta_value": str(delta_value),
                        "reason": "missing_price_for_sell",
                    }
                )
                committed_value[k] = current_value
                continue
            sell_value = -delta_value
            qty = sell_value / ref_price
            suggested.append(
                SuggestedTrade(
                    symbol=t.symbol,
                    market=t.market,
                    action="SELL",
                    qty=qty,
                    estimated_price=ref_price,
                    estimated_value=sell_value,
                    rationale=(
                        f"current {_pct_of(current_value, total_value)}% → "
                        f"target {t.target_pct}% (sell to reduce "
                        f"{_fmt_money(sell_value)})"
                    ),
                )
            )
            committed_value[k] = target_value

    # ---- pass 2: exit symbols not in targets at all -----------------------
    target_keys = {_key(t.symbol, t.market) for t in targets}
    for k, p in pos_by_key.items():
        if k in target_keys:
            continue
        if p.current_value <= _ZERO or p.qty <= _ZERO:
            continue
        # Always SELL — there's no target to compare against threshold,
        # so we honor min_trade_value here too (don't churn out a $5 SELL
        # just because the user dropped a tiny dust position from target).
        if p.current_value < min_trade_value:
            skipped.append(
                {
                    "symbol": p.symbol,
                    "market": p.market,
                    "target_pct": "0",
                    "delta_value": str(-p.current_value),
                    "reason": "exit_below_min_trade_value",
                }
            )
            # We DELIBERATELY do not credit this to committed_value — the
            # user chose to drop it from targets, so it should not skew
            # final_allocation_pct toward "we still hold it".
            continue
        if p.last_price <= _ZERO:
            skipped.append(
                {
                    "symbol": p.symbol,
                    "market": p.market,
                    "target_pct": "0",
                    "delta_value": str(-p.current_value),
                    "reason": "missing_price_for_sell",
                }
            )
            continue
        suggested.append(
            SuggestedTrade(
                symbol=p.symbol,
                market=p.market,
                action="SELL",
                qty=p.qty,
                estimated_price=p.last_price,
                estimated_value=p.current_value,
                rationale=(
                    f"exit position (current "
                    f"{_pct_of(p.current_value, total_value)}% → target 0%)"
                ),
            )
        )
        # Exited position contributes 0 to committed_value.

    # ---- after-state final_allocation_pct --------------------------------
    final_alloc: dict[str, Decimal] = {}
    if total_value > _ZERO:
        for k, v in committed_value.items():
            final_alloc[k] = (v / total_value * _HUNDRED) if total_value else _ZERO

    # ---- cash residual ---------------------------------------------------
    # Sum the value the user is committing to AFTER the rebalance; what's
    # left over (rounding + skip slack + exits) is cash.
    committed_total = sum(committed_value.values(), _ZERO)
    cash_residual = total_value - committed_total

    return RebalanceResult(
        total_portfolio_value=total_value,
        suggested_trades=suggested,
        final_allocation_pct=final_alloc,
        skipped_trades=skipped,
        cash_residual=cash_residual,
    )


# ── private formatters (rationale strings only) ────────────────────────────


def _pct_of(value: Decimal, total: Decimal) -> str:
    """Render ``value/total`` as a percentage string with 2dp. Falls back
    to ``0`` when total is non-positive so rationale never shows NaN/inf.
    The rationale string is for humans; ``Decimal`` precision is preserved
    inside ``estimated_value`` for downstream consumers."""
    if total <= _ZERO:
        return "0"
    pct = value / total * _HUNDRED
    # quantize-free str() keeps the result short and Decimal-faithful.
    return f"{pct:.2f}"


def _fmt_money(value: Decimal) -> str:
    """Strip trailing zeros for compact rationale output. Cosmetic only;
    callers wanting precise wire numbers should consume the dataclass."""
    return f"{value:.2f}"
