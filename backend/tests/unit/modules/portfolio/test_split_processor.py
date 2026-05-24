"""Unit tests for `app.modules.portfolio.split_processor`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md
      §5.1 / §7 — corporate actions / Phase 4+.

Coverage map:

  FORWARD splits:
    S01 4:1 doubles + halves cost (100@50 → 400@12.5)
    S02 3:2 happy path (100 → 150)
    S03 per-lot total-cost invariant preserved (parametrised)
    S04 multi-lot scaled in lockstep
    S05 2:1 clean — no fractional residue
    S06 3:2 on 1 share produces fractional (1 → 1.5)

  REVERSE splits:
    S07 1:5 collapse (500@1 → 100@5)
    S08 reverse creates fractional → CIL (123 @5 → 24 + CIL of 0.6 * mkt)
    S09 reverse total_new_qty < total_old_qty (sanity)

  Edge cases:
    S10 ratio_from <= 0 raises
    S11 ratio_to <= 0 raises
    S12 negative ratio raises (parametrised)
    S13 same ratio (3:3) is no-op
    S14 empty open_lots returns empty result
    S15 keep_fractional preserves decimals (no CIL)
    S16 round_to_nearest policy (>=0.5 up, else down)
    S17 cash_in_lieu_usd == 0 on clean split
    S18 ratio with high decimal precision preserved
    S19 direction mismatch (FORWARD declared but ratio_to < ratio_from)
    S20 round_down policy requires current_market_price
"""
from __future__ import annotations

from decimal import Decimal, getcontext

import pytest

from app.modules.portfolio.cost_basis import Lot
from app.modules.portfolio.split_processor import (
    SplitType,
    StockSplitInputs,
    compute_split_multiplier,
    process_stock_split,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _lot(
    lot_id: int,
    original: str,
    remaining: str,
    cost: str,
    exhausted: bool = False,
) -> Lot:
    return Lot(
        lot_id=lot_id,
        original_qty=Decimal(original),
        remaining_qty=Decimal(remaining),
        cost_per_unit=Decimal(cost),
        is_exhausted=exhausted,
    )


def _fwd(
    ratio_from: str,
    ratio_to: str,
    lots: list[Lot],
    policy: str = "round_down_cash_in_lieu",
    market_price: str | None = "100",
) -> StockSplitInputs:
    return StockSplitInputs(
        split_type=SplitType.FORWARD,
        ratio_from=Decimal(ratio_from),
        ratio_to=Decimal(ratio_to),
        open_lots=lots,
        fractional_policy=policy,
        current_market_price=(
            Decimal(market_price) if market_price is not None else None
        ),
    )


def _rev(
    ratio_from: str,
    ratio_to: str,
    lots: list[Lot],
    policy: str = "round_down_cash_in_lieu",
    market_price: str | None = "100",
) -> StockSplitInputs:
    return StockSplitInputs(
        split_type=SplitType.REVERSE,
        ratio_from=Decimal(ratio_from),
        ratio_to=Decimal(ratio_to),
        open_lots=lots,
        fractional_policy=policy,
        current_market_price=(
            Decimal(market_price) if market_price is not None else None
        ),
    )


# ---------------------------------------------------------------------------
# FORWARD splits
# ---------------------------------------------------------------------------


# S01 — 4:1 doubles shares, halves cost (canonical AAPL-style 4-for-1)
def test_forward_4_to_1_quadruples_shares_quarters_cost():
    lots = [_lot(1, "100", "100", "50")]
    res = process_stock_split(
        _fwd("1", "4", lots, policy="keep_fractional", market_price=None)
    )
    assert res.multiplier == Decimal("4")
    assert len(res.updated_lots) == 1
    new = res.updated_lots[0]
    assert new.lot_id == 1
    assert new.remaining_qty == Decimal("400")
    assert new.original_qty == Decimal("400")
    # 50 / 4 = 12.5 exact
    assert new.cost_per_unit == Decimal("12.5")
    # Invariant
    assert new.remaining_qty * new.cost_per_unit == Decimal("100") * Decimal("50")
    assert res.cash_in_lieu_usd == Decimal("0")


# S02 — 3:2 forward split happy path
def test_forward_3_to_2_split():
    lots = [_lot(1, "100", "100", "60")]
    res = process_stock_split(
        _fwd("2", "3", lots, policy="keep_fractional", market_price=None)
    )
    assert res.multiplier == Decimal("3") / Decimal("2")
    new = res.updated_lots[0]
    assert new.remaining_qty == Decimal("150")
    # 60 / 1.5 = 40
    assert new.cost_per_unit == Decimal("60") * Decimal("2") / Decimal("3")
    assert new.remaining_qty * new.cost_per_unit == Decimal("100") * Decimal("60")


# S03 — invariant preserved across various forward ratios
@pytest.mark.parametrize(
    ("frm", "to", "qty", "cost"),
    [
        ("1", "4", "100", "50"),
        ("2", "3", "200", "75"),
        ("1", "10", "10", "1000"),
        ("3", "7", "21", "33.33"),
    ],
)
def test_forward_preserves_total_cost_invariant(frm, to, qty, cost):
    lots = [_lot(1, qty, qty, cost)]
    res = process_stock_split(
        _fwd(frm, to, lots, policy="keep_fractional", market_price=None)
    )
    new = res.updated_lots[0]
    assert new.remaining_qty * new.cost_per_unit == Decimal(qty) * Decimal(cost)


# S04 — multi-lot scale lockstep
def test_forward_multi_lot_all_scaled():
    lots = [
        _lot(1, "100", "100", "50"),
        _lot(2, "200", "200", "60"),
        _lot(3, "50", "30", "70"),  # partial fill
    ]
    res = process_stock_split(
        _fwd("1", "2", lots, policy="keep_fractional", market_price=None)
    )
    assert res.multiplier == Decimal("2")
    assert len(res.updated_lots) == 3
    # Lot 1
    assert res.updated_lots[0].remaining_qty == Decimal("200")
    assert res.updated_lots[0].cost_per_unit == Decimal("25")
    # Lot 2
    assert res.updated_lots[1].remaining_qty == Decimal("400")
    assert res.updated_lots[1].cost_per_unit == Decimal("30")
    # Lot 3 — original 50 → 100, remaining 30 → 60
    assert res.updated_lots[2].original_qty == Decimal("100")
    assert res.updated_lots[2].remaining_qty == Decimal("60")
    assert res.updated_lots[2].cost_per_unit == Decimal("35")
    # Totals
    assert res.total_old_qty == Decimal("330")
    assert res.total_new_qty == Decimal("660")


# S05 — 2:1 clean (no fractional)
def test_forward_2_to_1_clean_no_fractional():
    lots = [_lot(1, "4", "4", "10")]
    res = process_stock_split(_fwd("1", "2", lots))
    new = res.updated_lots[0]
    assert new.remaining_qty == Decimal("8")
    assert new.cost_per_unit == Decimal("5")
    assert res.cash_in_lieu_usd == Decimal("0")


# S06 — 3:2 forward on 1 share produces fractional, default policy → CIL
def test_forward_3_to_2_creates_fractional_with_cil():
    lots = [_lot(1, "1", "1", "100")]
    # market price = 200
    inputs = StockSplitInputs(
        split_type=SplitType.FORWARD,
        ratio_from=Decimal("2"),
        ratio_to=Decimal("3"),
        open_lots=lots,
        fractional_policy="round_down_cash_in_lieu",
        current_market_price=Decimal("200"),
    )
    res = process_stock_split(inputs)
    new = res.updated_lots[0]
    # raw new_qty = 1.5 → floor 1
    assert new.remaining_qty == Decimal("1")
    # fractional 0.5 * 200 = 100
    assert res.cash_in_lieu_usd == Decimal("100.0")
    # Per-unit cost matches un-truncated split per-unit cost: 100 / 1.5
    expected_cost = Decimal("1") * Decimal("100") / (Decimal("1") * Decimal("3") / Decimal("2"))
    assert new.cost_per_unit == expected_cost


# ---------------------------------------------------------------------------
# REVERSE splits
# ---------------------------------------------------------------------------


# S07 — 1:5 reverse (collapse 5 shares into 1)
def test_reverse_1_to_5_reduces_shares_increases_cost():
    lots = [_lot(1, "500", "500", "1")]
    res = process_stock_split(
        _rev("5", "1", lots, policy="keep_fractional", market_price=None)
    )
    # multiplier = 1/5 = 0.2
    assert res.multiplier == Decimal("1") / Decimal("5")
    new = res.updated_lots[0]
    assert new.remaining_qty == Decimal("100")
    assert new.cost_per_unit == Decimal("5")
    # Invariant
    assert new.remaining_qty * new.cost_per_unit == Decimal("500") * Decimal("1")


# S08 — reverse fractional → CIL (123 shares, 1:5 reverse → 24.6 raw)
def test_reverse_creates_fractional_cash_in_lieu():
    lots = [_lot(1, "123", "123", "5")]
    inputs = StockSplitInputs(
        split_type=SplitType.REVERSE,
        ratio_from=Decimal("5"),
        ratio_to=Decimal("1"),
        open_lots=lots,
        fractional_policy="round_down_cash_in_lieu",
        current_market_price=Decimal("50"),
    )
    res = process_stock_split(inputs)
    new = res.updated_lots[0]
    # raw_new = 123 / 5 = 24.6 → floor 24
    assert new.remaining_qty == Decimal("24")
    # fractional 0.6 * 50 = 30.0
    assert res.cash_in_lieu_usd == Decimal("30.0")
    # Per-unit cost = (123 * 5) / 24.6 = 615 / 24.6 = 25.0
    expected = Decimal("123") * Decimal("5") / Decimal("24.6")
    assert new.cost_per_unit == expected


# S09 — reverse: total_new_qty < total_old_qty
def test_reverse_total_qty_decreases():
    lots = [
        _lot(1, "200", "200", "10"),
        _lot(2, "300", "300", "12"),
    ]
    res = process_stock_split(
        _rev("4", "1", lots, policy="keep_fractional", market_price=None)
    )
    assert res.total_old_qty == Decimal("500")
    assert res.total_new_qty == Decimal("125")
    assert res.total_new_qty < res.total_old_qty


# ---------------------------------------------------------------------------
# Edge cases / validation
# ---------------------------------------------------------------------------


# S10 — ratio_from = 0 raises
def test_ratio_from_zero_raises():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="ratio_from"):
        process_stock_split(
            _fwd("0", "4", lots, policy="keep_fractional", market_price=None)
        )


# S11 — ratio_to = 0 raises
def test_ratio_to_zero_raises():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="ratio_to"):
        process_stock_split(
            _fwd("1", "0", lots, policy="keep_fractional", market_price=None)
        )


# S12 — negative ratios raise
@pytest.mark.parametrize(
    ("frm", "to"),
    [("-1", "4"), ("1", "-4"), ("-2", "-3")],
)
def test_negative_ratio_raises(frm, to):
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError):
        process_stock_split(
            _fwd(frm, to, lots, policy="keep_fractional", market_price=None)
        )


# S13 — equal ratios (3:3) is a no-op
def test_same_ratio_is_noop():
    lots = [
        _lot(1, "100", "100", "50"),
        _lot(2, "200", "150", "60", exhausted=False),
    ]
    res = process_stock_split(
        _fwd("3", "3", lots, policy="keep_fractional", market_price=None)
    )
    assert res.multiplier == Decimal("1")
    for orig, new in zip(lots, res.updated_lots, strict=True):
        assert new.lot_id == orig.lot_id
        assert new.remaining_qty == orig.remaining_qty
        assert new.original_qty == orig.original_qty
        assert new.cost_per_unit == orig.cost_per_unit
        assert new.is_exhausted == orig.is_exhausted
        assert new is not orig  # fresh instance
    assert res.cash_in_lieu_usd == Decimal("0")
    assert res.total_old_qty == res.total_new_qty == Decimal("250")


# S14 — empty open_lots returns empty result
def test_empty_lots_returns_empty():
    res = process_stock_split(
        _fwd("1", "4", [], policy="keep_fractional", market_price=None)
    )
    assert res.updated_lots == []
    assert res.total_old_qty == Decimal("0")
    assert res.total_new_qty == Decimal("0")
    assert res.cash_in_lieu_usd == Decimal("0")
    assert res.multiplier == Decimal("4")


# S15 — keep_fractional preserves decimal new_qty, no CIL
def test_keep_fractional_policy_preserves_decimals():
    lots = [_lot(1, "1", "1", "100")]
    inputs = StockSplitInputs(
        split_type=SplitType.FORWARD,
        ratio_from=Decimal("2"),
        ratio_to=Decimal("3"),
        open_lots=lots,
        fractional_policy="keep_fractional",
    )
    res = process_stock_split(inputs)
    new = res.updated_lots[0]
    assert new.remaining_qty == Decimal("1") * Decimal("3") / Decimal("2")
    assert new.remaining_qty == Decimal("1.5")
    # Invariant
    assert new.remaining_qty * new.cost_per_unit == Decimal("1") * Decimal("100")
    assert res.cash_in_lieu_usd == Decimal("0")


# S16 — round_to_nearest: 1.5 → 2 (HALF_UP), 1.4 → 1
@pytest.mark.parametrize(
    ("ratio_from", "ratio_to", "remaining_qty", "expected_qty"),
    [
        ("2", "3", "1", "2"),    # 1.5 → 2 (HALF_UP)
        ("5", "7", "1", "1"),    # 1.4 → 1
        ("5", "8", "1", "2"),    # 1.6 → 2
        ("4", "1", "23", "6"),   # reverse: 5.75 → 6
    ],
)
def test_round_to_nearest_policy(ratio_from, ratio_to, remaining_qty, expected_qty):
    lots = [_lot(1, remaining_qty, remaining_qty, "100")]
    split_type = (
        SplitType.FORWARD
        if Decimal(ratio_to) >= Decimal(ratio_from)
        else SplitType.REVERSE
    )
    inputs = StockSplitInputs(
        split_type=split_type,
        ratio_from=Decimal(ratio_from),
        ratio_to=Decimal(ratio_to),
        open_lots=lots,
        fractional_policy="round_to_nearest",
    )
    res = process_stock_split(inputs)
    new = res.updated_lots[0]
    assert new.remaining_qty == Decimal(expected_qty)
    # Invariant preserved on rounded qty
    assert (
        new.remaining_qty * new.cost_per_unit
        == Decimal(remaining_qty) * Decimal("100")
    )
    assert res.cash_in_lieu_usd == Decimal("0")  # no CIL under this policy


# S17 — cash_in_lieu_usd == 0 on clean split (no residue)
def test_cash_in_lieu_zero_when_no_fractional():
    lots = [_lot(1, "100", "100", "50")]
    res = process_stock_split(_fwd("1", "4", lots, market_price="200"))
    assert res.cash_in_lieu_usd == Decimal("0")
    assert res.updated_lots[0].remaining_qty == Decimal("400")


# S18 — high-precision Decimal ratio preserved (no float coercion)
def test_decimal_precision_preserved():
    ctx_prec = getcontext().prec
    try:
        getcontext().prec = 50
        lots = [_lot(1, "300", "300", "99.99")]
        # Use a 1:9 reverse split — exact reciprocal repeating Decimal
        inputs = StockSplitInputs(
            split_type=SplitType.REVERSE,
            ratio_from=Decimal("9"),
            ratio_to=Decimal("1"),
            open_lots=lots,
            fractional_policy="keep_fractional",
        )
        res = process_stock_split(inputs)
        new = res.updated_lots[0]
        # remaining = 300 / 9 — repeating Decimal with current precision
        expected_qty = Decimal("300") / Decimal("9")
        assert new.remaining_qty == expected_qty
        # Invariant holds exactly under Decimal
        assert new.remaining_qty * new.cost_per_unit == Decimal("300") * Decimal("99.99")
    finally:
        getcontext().prec = ctx_prec


# S19 — direction mismatch
def test_forward_declared_with_reverse_ratio_raises():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="FORWARD"):
        process_stock_split(
            StockSplitInputs(
                split_type=SplitType.FORWARD,
                ratio_from=Decimal("5"),
                ratio_to=Decimal("1"),
                open_lots=lots,
                fractional_policy="keep_fractional",
            )
        )


def test_reverse_declared_with_forward_ratio_raises():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="REVERSE"):
        process_stock_split(
            StockSplitInputs(
                split_type=SplitType.REVERSE,
                ratio_from=Decimal("1"),
                ratio_to=Decimal("4"),
                open_lots=lots,
                fractional_policy="keep_fractional",
            )
        )


# S20 — round_down_cash_in_lieu policy requires current_market_price
def test_round_down_policy_requires_market_price():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="current_market_price"):
        process_stock_split(
            StockSplitInputs(
                split_type=SplitType.FORWARD,
                ratio_from=Decimal("2"),
                ratio_to=Decimal("3"),
                open_lots=lots,
                fractional_policy="round_down_cash_in_lieu",
                current_market_price=None,
            )
        )


# Bonus — compute_split_multiplier helper sanity
def test_compute_split_multiplier_basic():
    assert (
        compute_split_multiplier(SplitType.FORWARD, Decimal("1"), Decimal("4"))
        == Decimal("4")
    )
    assert compute_split_multiplier(
        SplitType.REVERSE, Decimal("5"), Decimal("1")
    ) == Decimal("1") / Decimal("5")


def test_compute_split_multiplier_zero_raises():
    with pytest.raises(ValueError):
        compute_split_multiplier(SplitType.FORWARD, Decimal("0"), Decimal("4"))
    with pytest.raises(ValueError):
        compute_split_multiplier(SplitType.FORWARD, Decimal("1"), Decimal("0"))


# Invalid policy string
def test_unknown_fractional_policy_raises():
    lots = [_lot(1, "10", "10", "5")]
    with pytest.raises(ValueError, match="fractional_policy"):
        process_stock_split(
            StockSplitInputs(
                split_type=SplitType.FORWARD,
                ratio_from=Decimal("1"),
                ratio_to=Decimal("2"),
                open_lots=lots,
                fractional_policy="banker_rounding",
            )
        )
