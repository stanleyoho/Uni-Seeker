"""Unit tests for `app.modules.portfolio.cost_basis`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.1 / §7.2.

Coverage:
  C01 apply_buy creates lot with correct cost_per_unit (fee embedded)
  C02 apply_buy rejects non-positive qty (delegated to FIFOEngine)
  C03 apply_sell — FIFO oldest-first ordering
  C04 apply_sell — cross multiple lots
  C05 apply_sell — insufficient shares raises
  C06 apply_sell — fees + tax reduce proceeds (realized loss)
  C07 average_cost — weighted average across lots
  C08 average_cost — empty / all-exhausted → 0
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.portfolio.cost_basis import (
    CostBasisInputs,
    InsufficientSharesError,
    Lot,
    apply_buy,
    apply_sell,
    average_cost,
)


# C01 — apply_buy creates a lot with fee folded into cost_per_unit
def test_C01_apply_buy_creates_lot_with_fee():
    res = apply_buy(
        lot_id=42,
        qty=Decimal("100"),
        price=Decimal("50"),
        fee=Decimal("100"),
    )
    # cost_per_unit = (50*100 + 100) / 100 = 51
    assert res.new_lot.lot_id == 42
    assert res.new_lot.original_qty == Decimal("100")
    assert res.new_lot.remaining_qty == Decimal("100")
    assert res.new_lot.cost_per_unit == Decimal("51")
    assert res.new_lot.is_exhausted is False


# C02 — apply_buy rejects non-positive qty
@pytest.mark.parametrize("bad_qty", [Decimal("0"), Decimal("-10")])
def test_C02_apply_buy_rejects_non_positive_qty(bad_qty):
    with pytest.raises(ValueError):
        apply_buy(lot_id=1, qty=bad_qty, price=Decimal("50"), fee=Decimal("0"))


# C03 — apply_sell consumes oldest lot first
def test_C03_apply_sell_fifo_order():
    lots = [
        Lot(
            lot_id=1,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("100"),
        ),
        Lot(
            lot_id=2,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("200"),
        ),
    ]
    res = apply_sell(
        CostBasisInputs(
            open_lots=lots,
            sell_qty=Decimal("50"),
            sell_price=Decimal("150"),
            sell_fee=Decimal("0"),
        )
    )
    # 50 shares consumed from lot 1 @100 cost; proceeds=7500, cost=5000 → +2500
    assert res.realized_pnl == Decimal("2500")
    assert res.qty_consumed == Decimal("50")
    assert res.updated_lots[0].remaining_qty == Decimal("50")
    assert res.updated_lots[1].remaining_qty == Decimal("100")  # untouched


# C04 — apply_sell crosses multiple lots
def test_C04_apply_sell_crosses_lots():
    lots = [
        Lot(
            lot_id=1,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("100"),
        ),
        Lot(
            lot_id=2,
            original_qty=Decimal("50"),
            remaining_qty=Decimal("50"),
            cost_per_unit=Decimal("120"),
        ),
    ]
    res = apply_sell(
        CostBasisInputs(
            open_lots=lots,
            sell_qty=Decimal("120"),
            sell_price=Decimal("150"),
            sell_fee=Decimal("0"),
        )
    )
    # Lot1 100@100 → 50_gain ×100 = 5000; Lot2 20@120 → 30 ×20 = 600 → 5600
    assert res.realized_pnl == Decimal("5600")
    assert res.updated_lots[0].is_exhausted is True
    assert res.updated_lots[1].remaining_qty == Decimal("30")


# C05 — apply_sell with qty > available raises
def test_C05_apply_sell_insufficient_raises():
    lots = [
        Lot(
            lot_id=1,
            original_qty=Decimal("10"),
            remaining_qty=Decimal("10"),
            cost_per_unit=Decimal("100"),
        ),
    ]
    with pytest.raises(InsufficientSharesError):
        apply_sell(
            CostBasisInputs(
                open_lots=lots,
                sell_qty=Decimal("50"),
                sell_price=Decimal("150"),
                sell_fee=Decimal("0"),
            )
        )


# C06 — apply_sell with sell-side fee + tax reduces proceeds
def test_C06_apply_sell_fee_and_tax():
    # Lot @101 cost (fee already embedded). Sell 100@100, fee=100, tax=300.
    # proceeds = 100*100 - 100 - 300 = 9600 ; cost = 101*100 = 10100 ; pnl = -500
    lots = [
        Lot(
            lot_id=1,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("101"),
        ),
    ]
    res = apply_sell(
        CostBasisInputs(
            open_lots=lots,
            sell_qty=Decimal("100"),
            sell_price=Decimal("100"),
            sell_fee=Decimal("100"),
            sell_tax=Decimal("300"),
        )
    )
    assert res.realized_pnl == Decimal("-500")


# C07 — average_cost is qty-weighted
def test_C07_average_cost_weighted():
    lots = [
        Lot(
            lot_id=1,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("50"),
        ),
        Lot(
            lot_id=2,
            original_qty=Decimal("300"),
            remaining_qty=Decimal("300"),
            cost_per_unit=Decimal("70"),
        ),
    ]
    # (100*50 + 300*70) / 400 = (5000 + 21000) / 400 = 65
    assert average_cost(lots) == Decimal("65")


# C08 — empty / all-exhausted returns 0
@pytest.mark.parametrize(
    "lots",
    [
        [],
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("0"),
                cost_per_unit=Decimal("50"),
                is_exhausted=True,
            )
        ],
    ],
)
def test_C08_average_cost_empty_or_exhausted(lots):
    assert average_cost(lots) == Decimal("0")
