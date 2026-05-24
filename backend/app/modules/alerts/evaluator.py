"""Pure rule evaluator — given a rule + market snapshot, decide if it
should fire.

Design constraints:
  - 100% pure: no DB, no httpx, no asyncio. Easy to unit-test with
    plain ``Decimal`` inputs.
  - All numeric comparisons run on ``Decimal``; the service layer is
    responsible for handing us ``Decimal`` (never ``float``).
  - Missing prices (None) are treated as "cannot evaluate" — the
    evaluator returns ``triggered=False`` with a diagnostic message.
    The service layer counts these as "skipped" rather than "errored"
    so a missing quote doesn't pause a rule.

Rule semantics
--------------
  POSITION_PRICE_DROP       — fires when last_price <= prev_close * (1 - threshold/100)
                              (PCT) OR last_price <= prev_close - threshold (ABSOLUTE).
                              "drop X%" matches Stanley's UX phrasing.
  POSITION_PRICE_RISE       — symmetric upper bound.
  POSITION_PNL_PCT_ABOVE    — fires when unrealized_pnl_pct >= threshold (PCT only).
  POSITION_PNL_PCT_BELOW    — fires when unrealized_pnl_pct <= threshold.
                              Negative thresholds are allowed (e.g. -10 = stop loss).
  PORTFOLIO_VALUE_ABOVE     — fires when total_value >= threshold (ABSOLUTE only).
  PORTFOLIO_VALUE_BELOW     — fires when total_value <= threshold.

Threshold sign convention
-------------------------
Always positive for DROP/RISE; PNL_PCT_BELOW accepts negative inputs
to encode stop-loss-style "fire if I'm down more than 10%".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping


class RuleType(str, Enum):
    POSITION_PRICE_DROP = "POSITION_PRICE_DROP"
    POSITION_PRICE_RISE = "POSITION_PRICE_RISE"
    PORTFOLIO_VALUE_ABOVE = "PORTFOLIO_VALUE_ABOVE"
    PORTFOLIO_VALUE_BELOW = "PORTFOLIO_VALUE_BELOW"
    POSITION_PNL_PCT_ABOVE = "POSITION_PNL_PCT_ABOVE"
    POSITION_PNL_PCT_BELOW = "POSITION_PNL_PCT_BELOW"


class ThresholdType(str, Enum):
    PCT = "PCT"
    ABSOLUTE = "ABSOLUTE"


_ZERO = Decimal("0")
_ONE_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PositionSnapshot:
    """One position's relevant fields for rule evaluation.

    quantity / avg_cost may be None when we only know a quote (e.g. the
    user pre-created a rule for a symbol they don't yet own — we still
    let PRICE_* rules fire because they only need quote data).
    """

    last_price: Decimal | None
    prev_close: Decimal | None
    quantity: Decimal | None = None
    avg_cost: Decimal | None = None
    unrealized_pnl_pct: Decimal | None = None


@dataclass(frozen=True)
class EvaluationContext:
    """Snapshot of relevant state at the moment of evaluation.

    ``positions`` is keyed by (symbol, market) to keep multi-market
    portfolios (e.g. NVDA on US_NASDAQ + a TW position) disambiguated.
    """

    portfolio_value: Decimal
    positions: Mapping[tuple[str, str], PositionSnapshot] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class EvaluationResult:
    triggered: bool
    actual_value: Decimal
    threshold: Decimal
    message: str


def _no_trigger(reason: str, threshold: Decimal) -> EvaluationResult:
    """Common factory for the "couldn't evaluate / didn't fire" path."""
    return EvaluationResult(
        triggered=False,
        actual_value=_ZERO,
        threshold=threshold,
        message=reason,
    )


def evaluate_rule(
    rule_type: RuleType | str,
    threshold: Decimal,
    threshold_type: ThresholdType | str,
    symbol: str | None,
    market: str | None,
    context: EvaluationContext,
) -> EvaluationResult:
    """Evaluate a single rule against ``context``.

    Returns an ``EvaluationResult``. Callers (the service) decide what
    to do on ``triggered=True`` — typically: send TG, mark rule as
    TRIGGERED, set ``last_triggered_at``.
    """
    # Normalise inputs so string-based callers (e.g. ORM rows) work too.
    rt = RuleType(rule_type) if isinstance(rule_type, str) else rule_type
    tt = (
        ThresholdType(threshold_type)
        if isinstance(threshold_type, str)
        else threshold_type
    )

    # Portfolio-wide rules ──────────────────────────────────────────────
    if rt is RuleType.PORTFOLIO_VALUE_ABOVE:
        # Only ABSOLUTE makes sense here; PCT against what baseline?
        if tt is not ThresholdType.ABSOLUTE:
            return _no_trigger(
                "portfolio_value rules require threshold_type=ABSOLUTE",
                threshold,
            )
        actual = context.portfolio_value
        triggered = actual >= threshold
        return EvaluationResult(
            triggered=triggered,
            actual_value=actual,
            threshold=threshold,
            message=(
                f"Portfolio value ${actual:,.2f} >= ${threshold:,.2f}"
                if triggered
                else f"Portfolio value ${actual:,.2f} below ${threshold:,.2f}"
            ),
        )

    if rt is RuleType.PORTFOLIO_VALUE_BELOW:
        if tt is not ThresholdType.ABSOLUTE:
            return _no_trigger(
                "portfolio_value rules require threshold_type=ABSOLUTE",
                threshold,
            )
        actual = context.portfolio_value
        triggered = actual <= threshold
        return EvaluationResult(
            triggered=triggered,
            actual_value=actual,
            threshold=threshold,
            message=(
                f"Portfolio value ${actual:,.2f} <= ${threshold:,.2f}"
                if triggered
                else f"Portfolio value ${actual:,.2f} above ${threshold:,.2f}"
            ),
        )

    # Position-scoped rules ────────────────────────────────────────────
    if symbol is None or market is None:
        return _no_trigger(
            "position rules require symbol + market", threshold
        )

    snapshot = context.positions.get((symbol, market))
    if snapshot is None:
        return _no_trigger(
            f"no snapshot for {symbol}/{market}", threshold
        )

    if rt is RuleType.POSITION_PRICE_DROP:
        return _eval_price_drop(symbol, market, threshold, tt, snapshot)
    if rt is RuleType.POSITION_PRICE_RISE:
        return _eval_price_rise(symbol, market, threshold, tt, snapshot)
    if rt is RuleType.POSITION_PNL_PCT_ABOVE:
        return _eval_pnl_above(symbol, market, threshold, tt, snapshot)
    if rt is RuleType.POSITION_PNL_PCT_BELOW:
        return _eval_pnl_below(symbol, market, threshold, tt, snapshot)

    # Should be unreachable thanks to the Enum coerce above.
    return _no_trigger(f"unknown rule_type {rt!r}", threshold)


# ── per-rule helpers ─────────────────────────────────────────────────


def _eval_price_drop(
    symbol: str,
    market: str,
    threshold: Decimal,
    tt: ThresholdType,
    snap: PositionSnapshot,
) -> EvaluationResult:
    if snap.last_price is None or snap.prev_close is None:
        return _no_trigger(
            f"{symbol}/{market}: missing quote", threshold
        )
    if tt is ThresholdType.PCT:
        # Drop percent expressed as a positive number; convert to a ratio
        # against prev_close to compare absolute prices.
        bound = snap.prev_close * (
            _ONE_HUNDRED - threshold
        ) / _ONE_HUNDRED
    else:
        bound = snap.prev_close - threshold
    triggered = snap.last_price <= bound
    pct_drop = (
        ((snap.prev_close - snap.last_price) / snap.prev_close)
        * _ONE_HUNDRED
        if snap.prev_close != _ZERO
        else _ZERO
    )
    msg = (
        f"{symbol} dropped {pct_drop:.2f}% "
        f"({snap.last_price} from {snap.prev_close})"
        if triggered
        else f"{symbol} drop {pct_drop:.2f}% below threshold"
    )
    return EvaluationResult(
        triggered=triggered,
        actual_value=snap.last_price,
        threshold=threshold,
        message=msg,
    )


def _eval_price_rise(
    symbol: str,
    market: str,
    threshold: Decimal,
    tt: ThresholdType,
    snap: PositionSnapshot,
) -> EvaluationResult:
    if snap.last_price is None or snap.prev_close is None:
        return _no_trigger(
            f"{symbol}/{market}: missing quote", threshold
        )
    if tt is ThresholdType.PCT:
        bound = snap.prev_close * (
            _ONE_HUNDRED + threshold
        ) / _ONE_HUNDRED
    else:
        bound = snap.prev_close + threshold
    triggered = snap.last_price >= bound
    pct_rise = (
        ((snap.last_price - snap.prev_close) / snap.prev_close)
        * _ONE_HUNDRED
        if snap.prev_close != _ZERO
        else _ZERO
    )
    msg = (
        f"{symbol} rose {pct_rise:.2f}% "
        f"({snap.last_price} from {snap.prev_close})"
        if triggered
        else f"{symbol} rise {pct_rise:.2f}% below threshold"
    )
    return EvaluationResult(
        triggered=triggered,
        actual_value=snap.last_price,
        threshold=threshold,
        message=msg,
    )


def _eval_pnl_above(
    symbol: str,
    market: str,
    threshold: Decimal,
    tt: ThresholdType,
    snap: PositionSnapshot,
) -> EvaluationResult:
    # PNL_PCT inherently a percentage — ABSOLUTE doesn't make sense.
    if tt is not ThresholdType.PCT:
        return _no_trigger(
            "pnl_pct rules require threshold_type=PCT", threshold
        )
    if snap.unrealized_pnl_pct is None:
        return _no_trigger(
            f"{symbol}/{market}: no P&L data", threshold
        )
    actual = snap.unrealized_pnl_pct
    triggered = actual >= threshold
    return EvaluationResult(
        triggered=triggered,
        actual_value=actual,
        threshold=threshold,
        message=(
            f"{symbol} unrealized P&L {actual:.2f}% >= {threshold}%"
            if triggered
            else f"{symbol} unrealized P&L {actual:.2f}% below threshold"
        ),
    )


def _eval_pnl_below(
    symbol: str,
    market: str,
    threshold: Decimal,
    tt: ThresholdType,
    snap: PositionSnapshot,
) -> EvaluationResult:
    if tt is not ThresholdType.PCT:
        return _no_trigger(
            "pnl_pct rules require threshold_type=PCT", threshold
        )
    if snap.unrealized_pnl_pct is None:
        return _no_trigger(
            f"{symbol}/{market}: no P&L data", threshold
        )
    actual = snap.unrealized_pnl_pct
    triggered = actual <= threshold
    return EvaluationResult(
        triggered=triggered,
        actual_value=actual,
        threshold=threshold,
        message=(
            f"{symbol} unrealized P&L {actual:.2f}% <= {threshold}%"
            if triggered
            else f"{symbol} unrealized P&L {actual:.2f}% above threshold"
        ),
    )


__all__ = [
    "EvaluationContext",
    "EvaluationResult",
    "PositionSnapshot",
    "RuleType",
    "ThresholdType",
    "evaluate_rule",
]
