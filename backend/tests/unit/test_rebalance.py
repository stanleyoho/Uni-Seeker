"""Unit tests for rebalance alert calculator — T21–T28."""

from __future__ import annotations

from decimal import Decimal

from app.modules.trade_journal.rebalance import (
    AllocationRuleData,
    PositionData,
    compute_account_alerts,
)


def _rule(
    symbol: str,
    target: str,
    lower: str = "0.03",
    upper: str = "0.03",
    active: bool = True,
) -> AllocationRuleData:
    return AllocationRuleData(
        symbol=symbol,
        target_weight=Decimal(target),
        lower_threshold=Decimal(lower),
        upper_threshold=Decimal(upper),
        is_active=active,
    )


def _pos(symbol: str, value: str) -> PositionData:
    return PositionData(symbol=symbol, market_value=Decimal(value))


# T21: within range — no alert
def test_T21_within_range():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "210"), _pos("CASH", "790")]  # 21% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []


# T22: over upper threshold
def test_T22_over_upper():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "245")]  # 24.5% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert len(alerts) == 1
    assert alerts[0].direction == "over"
    assert alerts[0].deviation == Decimal("0.0450")


# T23: under lower threshold
def test_T23_under_lower():
    rules = [_rule("2330.TW", "0.20")]
    positions = [_pos("2330.TW", "150")]  # 15% of 1000
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert len(alerts) == 1
    assert alerts[0].direction == "under"
    assert alerts[0].deviation == Decimal("-0.0500")


# T24: within upper threshold exactly (boundary)
def test_T24_exactly_at_upper_boundary():
    # target=20%, upper_threshold=3% → 23% should NOT trigger (deviation=3% = threshold, not >)
    rules = [_rule("2330.TW", "0.20", upper="0.03")]
    positions = [_pos("2330.TW", "230")]  # exactly 23%
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []


# T25: just over upper threshold
def test_T25_just_over_upper():
    # target=20%, upper_threshold=3% → 23.01% SHOULD trigger
    rules = [_rule("2330.TW", "0.20", upper="0.03")]
    positions = [_pos("2330.TW", "230.1")]  # 23.01%
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert len(alerts) == 1
    assert alerts[0].direction == "over"


# T26: zero total value — no crash
def test_T26_zero_total_value():
    rules = [_rule("2330.TW", "0.20")]
    positions = []
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("0"))
    assert alerts == []


# T27: no rule for symbol — no alert
def test_T27_no_rule_for_symbol():
    rules = []
    positions = [_pos("2330.TW", "200")]
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []


# T28: inactive rule — no alert
def test_T28_inactive_rule():
    rules = [_rule("2330.TW", "0.20", active=False)]
    positions = [_pos("2330.TW", "500")]  # 50% — way over, but rule inactive
    alerts = compute_account_alerts(rules=rules, positions=positions, total_value=Decimal("1000"))
    assert alerts == []
