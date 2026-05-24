"""Unit tests for `app.modules.portfolio.rebalancing`.

Pure module — no DB, no HTTP. Covers the algorithm + validation + edges
documented in the module docstring.

Coverage (16 cases):
  Compute (9):
    R01 simple 2-symbol 50/50, already balanced → no trades
    R02 need to buy more (current 30% → target 60%)
    R03 need to sell some (current 60% → target 30%)
    R04 new symbol in target, absent from current → full BUY
    R05 exit symbol in current, absent from target → full SELL
    R06 mixed buy + sell combo
    R07 min_trade_threshold skip (delta < threshold)
    R08 cash residual computed from skip slack
    R09 final_allocation_pct after trades
  Validation (4):
    R10 invalid target sum != 100 raises
    R11 negative target_pct raises
    R12 duplicate target symbol raises
    R13 empty targets → all positions become SELLs
  Edge (3):
    R14 zero total portfolio value (empty positions, non-trivial targets)
    R15 min_trade_value == 0 disables skip
    R16 decimal precision preserved (no float artifacts)
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.portfolio.rebalancing import (
    CurrentPosition,
    RebalanceResult,
    SuggestedTrade,
    TargetAllocation,
    compute_rebalance,
    validate_targets,
)

# ── helpers ───────────────────────────────────────────────────────────────


def _pos(
    symbol: str,
    qty: str,
    last_price: str,
    market: str = "TW_TWSE",
) -> CurrentPosition:
    q = Decimal(qty)
    p = Decimal(last_price)
    return CurrentPosition(
        symbol=symbol,
        market=market,
        qty=q,
        last_price=p,
        current_value=q * p,
    )


def _tgt(symbol: str, pct: str, market: str = "TW_TWSE") -> TargetAllocation:
    return TargetAllocation(
        symbol=symbol, market=market, target_pct=Decimal(pct)
    )


def _find(
    trades: list[SuggestedTrade], symbol: str
) -> SuggestedTrade | None:
    return next((t for t in trades if t.symbol == symbol), None)


# ═══════════════════════════════════════════════════════════════════════════
# Compute cases
# ═══════════════════════════════════════════════════════════════════════════


def test_R01_simple_2_symbol_50_50_already_balanced():
    """Already-balanced portfolio → both deltas below default $100 threshold
    so no trades suggested. ``final_allocation_pct`` still reflects the
    50/50 split (we credit each symbol's current value when skipping)."""
    positions = [
        _pos("2330", qty="100", last_price="500"),  # value 50_000
        _pos("0050", qty="500", last_price="100"),  # value 50_000
    ]
    targets = [_tgt("2330", "50"), _tgt("0050", "50")]
    result = compute_rebalance(positions, targets)

    assert result.suggested_trades == []
    assert result.total_portfolio_value == Decimal("100000")
    # Final alloc reflects committed-current values (still 50/50).
    assert result.final_allocation_pct["2330|TW_TWSE"] == Decimal("50")
    assert result.final_allocation_pct["0050|TW_TWSE"] == Decimal("50")
    # Cash residual is zero — we committed the whole portfolio (just
    # skipped trades, but committed_value still equals current_value).
    assert result.cash_residual == Decimal("0")


def test_R02_need_to_buy_more():
    """30% current → 60% target → BUY to fill the gap."""
    positions = [
        _pos("AAPL", qty="100", last_price="100"),  # value 10_000 (50%)
        _pos("MSFT", qty="100", last_price="100"),  # value 10_000 (50%)
    ]
    # Want 70% AAPL, 30% MSFT.
    targets = [
        _tgt("AAPL", "70", market="US_NASDAQ"),
        _tgt("MSFT", "30", market="US_NASDAQ"),
    ]
    # Wrong market in pos → we need to align. Reuse same market here:
    positions = [
        _pos("AAPL", qty="100", last_price="100", market="US_NASDAQ"),
        _pos("MSFT", qty="100", last_price="100", market="US_NASDAQ"),
    ]
    result = compute_rebalance(positions, targets)

    buy = _find(result.suggested_trades, "AAPL")
    sell = _find(result.suggested_trades, "MSFT")
    assert buy is not None and buy.action == "BUY"
    # delta_value = 20_000 * 0.70 - 10_000 = 4_000 → 40 shares @ 100.
    assert buy.qty == Decimal("40")
    assert buy.estimated_value == Decimal("4000")
    assert sell is not None and sell.action == "SELL"
    assert sell.qty == Decimal("40")


def test_R03_need_to_sell_some():
    """60% current → 30% target → SELL the excess."""
    positions = [
        _pos("2330", qty="120", last_price="500"),  # value 60_000 (60%)
        _pos("0050", qty="400", last_price="100"),  # value 40_000 (40%)
    ]
    targets = [_tgt("2330", "30"), _tgt("0050", "70")]
    result = compute_rebalance(positions, targets)

    sell = _find(result.suggested_trades, "2330")
    buy = _find(result.suggested_trades, "0050")
    assert sell.action == "SELL"
    # target 30_000, current 60_000 → SELL value 30_000 → qty 60 @ 500.
    assert sell.qty == Decimal("60")
    assert sell.estimated_value == Decimal("30000")
    assert buy.action == "BUY"
    # target 70_000, current 40_000 → BUY 30_000 → qty 300 @ 100.
    assert buy.qty == Decimal("300")


def test_R04_new_symbol_in_target_not_current():
    """Target has a symbol we don't currently hold — without a price ref
    in the current portfolio the planner can't quote a BUY, so it
    surfaces a skip with ``missing_price_for_buy``. The other symbol gets
    a full SELL because target wants the new one at 100%."""
    positions = [
        _pos("OLD", qty="100", last_price="50"),  # value 5_000
    ]
    targets = [_tgt("NEW", "100")]  # 100% in something we don't hold
    result = compute_rebalance(positions, targets)

    # NEW gets skipped due to missing price — there's no current row.
    skipped_symbols = {s["symbol"] for s in result.skipped_trades}
    assert "NEW" in skipped_symbols
    # OLD must be exited because it's not in targets.
    old = _find(result.suggested_trades, "OLD")
    assert old.action == "SELL"
    assert old.qty == Decimal("100")


def test_R05_exit_symbol_in_current_not_target():
    """Symbol present in current, absent from targets → full SELL."""
    positions = [
        _pos("DROP", qty="100", last_price="100"),  # value 10_000
        _pos("KEEP", qty="100", last_price="100"),  # value 10_000
    ]
    # Only target KEEP at 100% — DROP must be sold.
    targets = [_tgt("KEEP", "100")]
    result = compute_rebalance(positions, targets)

    drop = _find(result.suggested_trades, "DROP")
    assert drop is not None
    assert drop.action == "SELL"
    assert drop.qty == Decimal("100")
    # KEEP needs to go 50% → 100%: BUY for 10_000.
    keep = _find(result.suggested_trades, "KEEP")
    assert keep.action == "BUY"
    assert keep.estimated_value == Decimal("10000")


def test_R06_mixed_buy_sell_combo():
    """Three positions, three targets, one of each direction + one hold."""
    positions = [
        _pos("A", qty="100", last_price="100"),  # value 10_000 (25%)
        _pos("B", qty="200", last_price="100"),  # value 20_000 (50%)
        _pos("C", qty="100", last_price="100"),  # value 10_000 (25%)
    ]
    targets = [
        _tgt("A", "50"),  # buy 10k
        _tgt("B", "25"),  # sell 10k
        _tgt("C", "25"),  # hold (delta 0 — but skipped below threshold)
    ]
    result = compute_rebalance(positions, targets)

    actions = {t.symbol: t.action for t in result.suggested_trades}
    assert actions["A"] == "BUY"
    assert actions["B"] == "SELL"
    # C is already at target → skipped (delta 0 < $100 threshold).
    assert "C" not in actions
    assert any(s["symbol"] == "C" for s in result.skipped_trades)


def test_R07_min_trade_threshold_skip():
    """delta_value below threshold should be skipped (no trade emitted)."""
    positions = [
        _pos("X", qty="100", last_price="100"),  # value 10_000 (50%)
        _pos("Y", qty="100", last_price="100"),  # value 10_000 (50%)
    ]
    # Target 50.4% / 49.6% → delta = 80, threshold default = 100.
    targets = [_tgt("X", "50.4"), _tgt("Y", "49.6")]
    result = compute_rebalance(positions, targets, min_trade_value=Decimal("100"))

    assert result.suggested_trades == []
    skipped_keys = {s["symbol"] for s in result.skipped_trades}
    assert skipped_keys == {"X", "Y"}
    # Both have "below_min_trade_value" reason.
    assert all(
        s["reason"] == "below_min_trade_value" for s in result.skipped_trades
    )


def test_R08_cash_residual_computed():
    """Skipped trades + exits leave residual cash. We track this so the
    UI can warn "$X is unallocated"."""
    positions = [
        _pos("KEEP", qty="500", last_price="100"),  # value 50_000
        # Tiny dust position — its $50 value falls under the default $100
        # min-trade threshold; it gets skipped as exit.
        _pos("DUST", qty="1", last_price="50"),  # value 50
    ]
    # Target 100% KEEP → KEEP needs to go 50_050 * 1.0 - 50_000 = 50.
    # That 50 BUY also falls under threshold → KEEP itself gets skipped.
    # Net: KEEP committed at its current value (50_000), DUST not credited.
    # Residual = total_value - committed_value = 50_050 - 50_000 = 50.
    targets = [_tgt("KEEP", "100")]
    result = compute_rebalance(positions, targets)

    assert result.cash_residual == Decimal("50")


def test_R09_final_allocation_pct_after_trades():
    """After-state allocation reflects the targets the user committed to."""
    positions = [
        _pos("A", qty="100", last_price="100"),  # 50%
        _pos("B", qty="100", last_price="100"),  # 50%
    ]
    targets = [_tgt("A", "70"), _tgt("B", "30")]
    result = compute_rebalance(positions, targets)

    # Both trades clear the $100 threshold → committed at target values.
    assert result.final_allocation_pct["A|TW_TWSE"] == Decimal("70")
    assert result.final_allocation_pct["B|TW_TWSE"] == Decimal("30")


# ═══════════════════════════════════════════════════════════════════════════
# Validation cases
# ═══════════════════════════════════════════════════════════════════════════


def test_R10_invalid_target_sum_not_100_raises():
    targets = [_tgt("A", "50"), _tgt("B", "30")]  # sum = 80
    with pytest.raises(ValueError, match="sum.*100"):
        validate_targets(targets)


def test_R11_negative_target_pct_raises():
    targets = [_tgt("A", "120"), _tgt("B", "-20")]
    with pytest.raises(ValueError, match="must be ≥ 0"):
        validate_targets(targets)


def test_R12_duplicate_target_symbol_raises():
    targets = [_tgt("A", "60"), _tgt("A", "40")]
    with pytest.raises(ValueError, match="duplicate target"):
        validate_targets(targets)


def test_R13_empty_targets_returns_all_sell():
    """Empty targets is legal — interpreted as 'exit everything'."""
    positions = [
        _pos("A", qty="100", last_price="100"),
        _pos("B", qty="50", last_price="200"),
    ]
    result = compute_rebalance(positions, [], min_trade_value=Decimal("0"))

    # Both positions become full SELLs.
    assert {t.symbol for t in result.suggested_trades} == {"A", "B"}
    assert all(t.action == "SELL" for t in result.suggested_trades)


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_R14_zero_total_portfolio_value():
    """Empty positions → no money to allocate → every target lands in
    the skipped list (delta = 0 - 0 = 0 < threshold) and no trades."""
    result = compute_rebalance(
        positions=[],
        targets=[_tgt("A", "60"), _tgt("B", "40")],
    )
    assert result.suggested_trades == []
    assert result.total_portfolio_value == Decimal("0")
    assert result.cash_residual == Decimal("0")


def test_R15_min_trade_value_zero_no_skip():
    """min_trade_value=0 disables the skip threshold entirely."""
    positions = [
        _pos("A", qty="100", last_price="100"),  # 50%
        _pos("B", qty="100", last_price="100"),  # 50%
    ]
    targets = [_tgt("A", "50.5"), _tgt("B", "49.5")]
    result = compute_rebalance(
        positions, targets, min_trade_value=Decimal("0")
    )
    # Tiny deltas still produce trades.
    assert len(result.suggested_trades) == 2
    actions = {t.symbol: t.action for t in result.suggested_trades}
    assert actions == {"A": "BUY", "B": "SELL"}


def test_R16_decimal_precision_preserved():
    """No float artifacts — output must be exact Decimal arithmetic."""
    positions = [
        _pos("A", qty="3", last_price="100.10"),  # 300.30
        _pos("B", qty="3", last_price="100.20"),  # 300.60
    ]
    # Target 1/3, 1/3, 1/3 doesn't sum nicely → use clean split.
    targets = [_tgt("A", "60"), _tgt("B", "40")]
    result = compute_rebalance(
        positions, targets, min_trade_value=Decimal("0")
    )

    # total_value = 300.30 + 300.60 = 600.90
    # A target = 600.90 * 0.6 = 360.54; current 300.30; delta 60.24
    a_buy = _find(result.suggested_trades, "A")
    assert a_buy.estimated_value == Decimal("60.24")
    # Total value should be the Decimal-exact sum.
    assert result.total_portfolio_value == Decimal("600.90")
