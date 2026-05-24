"""Portfolio P&L — pure functions, Decimal throughout.

Implements spec §7.1 / §7.3 / §7.4. **No DB, no SQLAlchemy, no float.**

Edge-case contract (spec §7):
  - `qty == 0`            → unrealized = 0, pct = 0 (no position)
  - `prev_close == 0`     → delta_pct = 0 (avoid div-by-zero)
  - `avg_cost == 0`       → unrealized_pnl_pct = 0 (avoid div-by-zero)
  - `total_cost == 0`     → gain_simple_pct = 0 (all closed)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "DailyChange",
    "MultiCurrencyPortfolioSummary",
    "PortfolioSummary",
    "UnrealizedPnL",
    "daily_change",
    "summarize",
    "unrealized",
]

_ZERO = Decimal("0")


@dataclass
class UnrealizedPnL:
    qty: Decimal
    avg_cost: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal


@dataclass
class DailyChange:
    last_price: Decimal
    prev_close: Decimal
    delta_per_share: Decimal
    delta_total: Decimal  # delta_per_share * qty
    delta_pct: Decimal


@dataclass
class PortfolioSummary:
    total_cost: Decimal
    total_value: Decimal
    total_unrealized_pnl: Decimal
    total_daily_change: Decimal
    gain_simple: Decimal  # Q6 (A): total_value - total_cost
    gain_simple_pct: Decimal


@dataclass
class MultiCurrencyPortfolioSummary:
    """Phase 4+ cross-currency aggregate.

    Wraps a base-currency `PortfolioSummary` with two breakdown maps so the
    UI can render per-currency KPI slices (e.g. "USD subtotal", "JPY
    subtotal") alongside the converted base-currency total.

    - `base_currency`: the ISO code the totals are expressed in.
    - `summary`: totals in `base_currency` (multi-currency sum already
      converted via FX rates).
    - `by_currency_native`: per-currency `PortfolioSummary` in that
      currency's own units (no conversion). The user's native view.
    - `by_currency_in_base`: per-currency `(total_cost, total_value)` pair
      already converted to `base_currency`. Used for stacked bar / pie
      breakdowns where every slice must share the same unit.
    - `rates_used`: snapshot of the FX rates applied (ccy → base
      multiplier). Surfaced for transparency / audit.
    """

    base_currency: str
    summary: PortfolioSummary
    by_currency_native: dict[str, PortfolioSummary]
    by_currency_in_base: dict[str, tuple[Decimal, Decimal]]
    rates_used: dict[str, Decimal]


def unrealized(
    qty: Decimal, avg_cost: Decimal, last_price: Decimal
) -> UnrealizedPnL:
    """Per-position unrealized P&L (spec §7.1).

    unrealized_pnl     = (last_price - avg_cost) * qty
    unrealized_pnl_pct = unrealized_pnl / (avg_cost * qty)

    Edge cases (see module docstring).
    """
    if qty == _ZERO:
        return UnrealizedPnL(
            qty=_ZERO,
            avg_cost=avg_cost,
            last_price=last_price,
            unrealized_pnl=_ZERO,
            unrealized_pnl_pct=_ZERO,
        )

    pnl = (last_price - avg_cost) * qty
    total_cost = avg_cost * qty
    if total_cost == _ZERO:
        # avg_cost == 0 (e.g. free shares) → pct undefined
        pct = _ZERO
    else:
        pct = pnl / total_cost
    return UnrealizedPnL(
        qty=qty,
        avg_cost=avg_cost,
        last_price=last_price,
        unrealized_pnl=pnl,
        unrealized_pnl_pct=pct,
    )


def daily_change(
    qty: Decimal, last_price: Decimal, prev_close: Decimal
) -> DailyChange:
    """Per-position daily change (spec §7.3).

    delta_per_share = last_price - prev_close
    delta_total     = delta_per_share * qty
    delta_pct       = delta_per_share / prev_close

    Edge cases:
      - qty == 0        → delta_total = 0 (delta_per_share/delta_pct still meaningful)
      - prev_close == 0 → delta_pct = 0
    """
    delta_per_share = last_price - prev_close
    delta_total = delta_per_share * qty
    if prev_close == _ZERO:
        delta_pct = _ZERO
    else:
        delta_pct = delta_per_share / prev_close
    return DailyChange(
        last_price=last_price,
        prev_close=prev_close,
        delta_per_share=delta_per_share,
        delta_total=delta_total,
        delta_pct=delta_pct,
    )


def summarize(
    positions: list[tuple[Decimal, Decimal, Decimal, Decimal]],
) -> PortfolioSummary:
    """Aggregate per-position numbers into a portfolio-wide summary.

    Input: list of `(qty, avg_cost, last_price, prev_close)` tuples.
    Output: see `PortfolioSummary`.

    Implements Q6 (A) — `gain_simple = total_value - total_cost` (spec §7.4),
    counting only currently-held positions (caller must filter out `is_closed`).

    Edge cases:
      - empty list      → all fields 0
      - all qty == 0    → all fields 0
      - total_cost == 0 → gain_simple_pct = 0
    """
    total_cost = _ZERO
    total_value = _ZERO
    total_unrealized = _ZERO
    total_daily = _ZERO

    for qty, avg_cost, last_price, prev_close in positions:
        if qty == _ZERO:
            continue
        cost = avg_cost * qty
        value = last_price * qty
        total_cost += cost
        total_value += value
        total_unrealized += value - cost
        total_daily += (last_price - prev_close) * qty

    gain_simple = total_value - total_cost
    if total_cost == _ZERO:
        gain_simple_pct = _ZERO
    else:
        gain_simple_pct = gain_simple / total_cost

    return PortfolioSummary(
        total_cost=total_cost,
        total_value=total_value,
        total_unrealized_pnl=total_unrealized,
        total_daily_change=total_daily,
        gain_simple=gain_simple,
        gain_simple_pct=gain_simple_pct,
    )
