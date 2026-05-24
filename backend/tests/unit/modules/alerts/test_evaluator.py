"""Unit tests for app.modules.alerts.evaluator — pure rule evaluator."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.alerts.evaluator import (
    EvaluationContext,
    PositionSnapshot,
    RuleType,
    ThresholdType,
    evaluate_rule,
)


def _ctx(
    *,
    portfolio_value: str = "0",
    positions: dict[tuple[str, str], PositionSnapshot] | None = None,
) -> EvaluationContext:
    return EvaluationContext(
        portfolio_value=Decimal(portfolio_value),
        positions=positions or {},
    )


# ── PRICE_DROP ──────────────────────────────────────────────────────────


def test_price_drop_pct_triggers_when_close_drops_more_than_threshold() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("89"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True


def test_price_drop_pct_no_trigger_when_drop_below_threshold() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("95"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is False


def test_price_drop_absolute_triggers() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("85"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),  # $10 absolute
        ThresholdType.ABSOLUTE,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True


# ── PRICE_RISE ──────────────────────────────────────────────────────────


def test_price_rise_pct_triggers() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("115"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_RISE,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True


def test_price_rise_no_trigger_when_flat() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("100"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_RISE,
        Decimal("5"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is False


# ── PORTFOLIO_VALUE ─────────────────────────────────────────────────────


def test_portfolio_value_above_triggers() -> None:
    ctx = _ctx(portfolio_value="1500000")
    result = evaluate_rule(
        RuleType.PORTFOLIO_VALUE_ABOVE,
        Decimal("1000000"),
        ThresholdType.ABSOLUTE,
        None,
        None,
        ctx,
    )
    assert result.triggered is True


def test_portfolio_value_above_below_does_not_trigger() -> None:
    ctx = _ctx(portfolio_value="900000")
    result = evaluate_rule(
        RuleType.PORTFOLIO_VALUE_ABOVE,
        Decimal("1000000"),
        ThresholdType.ABSOLUTE,
        None,
        None,
        ctx,
    )
    assert result.triggered is False


def test_portfolio_value_below_triggers() -> None:
    ctx = _ctx(portfolio_value="500000")
    result = evaluate_rule(
        RuleType.PORTFOLIO_VALUE_BELOW,
        Decimal("800000"),
        ThresholdType.ABSOLUTE,
        None,
        None,
        ctx,
    )
    assert result.triggered is True


def test_portfolio_value_rejects_pct_threshold() -> None:
    ctx = _ctx(portfolio_value="500000")
    result = evaluate_rule(
        RuleType.PORTFOLIO_VALUE_ABOVE,
        Decimal("10"),
        ThresholdType.PCT,
        None,
        None,
        ctx,
    )
    assert result.triggered is False
    assert "ABSOLUTE" in result.message


# ── PNL_PCT ─────────────────────────────────────────────────────────────


def test_pnl_above_triggers() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("120"),
        prev_close=Decimal("118"),
        unrealized_pnl_pct=Decimal("12"),
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PNL_PCT_ABOVE,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True


def test_pnl_below_negative_threshold_triggers_on_loss() -> None:
    """Stop-loss style: fire when -15% <= -10% (i.e. lost more than 10%)."""
    snap = PositionSnapshot(
        last_price=Decimal("85"),
        prev_close=Decimal("90"),
        unrealized_pnl_pct=Decimal("-15"),
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PNL_PCT_BELOW,
        Decimal("-10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True


def test_pnl_rejects_absolute_threshold() -> None:
    snap = PositionSnapshot(
        last_price=Decimal("100"),
        prev_close=Decimal("100"),
        unrealized_pnl_pct=Decimal("5"),
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PNL_PCT_ABOVE,
        Decimal("100"),
        ThresholdType.ABSOLUTE,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is False


# ── edge cases ──────────────────────────────────────────────────────────


def test_missing_snapshot_does_not_trigger() -> None:
    ctx = _ctx(positions={})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is False
    assert "no snapshot" in result.message


def test_missing_quote_does_not_trigger() -> None:
    snap = PositionSnapshot(last_price=None, prev_close=None)
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),
        ThresholdType.PCT,
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is False


def test_position_rule_without_symbol_does_not_trigger() -> None:
    ctx = _ctx()
    result = evaluate_rule(
        RuleType.POSITION_PRICE_DROP,
        Decimal("10"),
        ThresholdType.PCT,
        None,
        None,
        ctx,
    )
    assert result.triggered is False


def test_string_inputs_are_coerced() -> None:
    """Rule type/threshold_type passed as plain strings still work."""
    snap = PositionSnapshot(
        last_price=Decimal("85"), prev_close=Decimal("100")
    )
    ctx = _ctx(positions={("NVDA", "US_NASDAQ"): snap})
    result = evaluate_rule(
        "POSITION_PRICE_DROP",
        Decimal("10"),
        "PCT",
        "NVDA",
        "US_NASDAQ",
        ctx,
    )
    assert result.triggered is True
