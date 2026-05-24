"""Unit tests for `app.modules.portfolio.dividend_processor`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.1 / §7.

Coverage:
  CASH:
    D01 happy path — qty * amount - tax
    D02 zero withholding tax
    D03 raises when tax > total
    D04 zero qty returns zero (legitimate — no shares held that day)
    D05 realized_pnl_delta == net_amount invariant
    D-neg negative input rejection (parametrised)

  STOCK:
    D06 happy path — single lot ratio 0.1
    D07 per-lot total-cost invariant preserved
    D08 multiple lots all scaled correctly
    D09 ratio=0 is a no-op (returns copies)
    D10 negative ratio raises
    D11 empty lots returns empty result
    D12 odd-ratio decimal precision (no float coercion)
"""
from __future__ import annotations

from decimal import Decimal, getcontext

import pytest

from app.modules.portfolio.cost_basis import Lot
from app.modules.portfolio.dividend_processor import (
    CashDividendInputs,
    StockDividendInputs,
    process_cash_dividend,
    process_stock_dividend,
)

# ---------------------------------------------------------------------------
# CASH dividend
# ---------------------------------------------------------------------------


# D01 — happy path
def test_cash_dividend_happy_path():
    res = process_cash_dividend(
        CashDividendInputs(
            qty_at_record=Decimal("100"),
            amount_per_share=Decimal("2.5"),
            withholding_tax=Decimal("0.5"),
        )
    )
    assert res.total_amount == Decimal("250.0")
    assert res.net_amount == Decimal("249.5")
    assert res.realized_pnl_delta == Decimal("249.5")


# D02 — zero withholding tax
def test_cash_dividend_zero_tax():
    res = process_cash_dividend(
        CashDividendInputs(
            qty_at_record=Decimal("200"),
            amount_per_share=Decimal("3"),
            withholding_tax=Decimal("0"),
        )
    )
    assert res.total_amount == Decimal("600")
    assert res.net_amount == Decimal("600")
    assert res.realized_pnl_delta == Decimal("600")


# D03 — tax > total raises
def test_cash_dividend_raises_when_tax_exceeds_total():
    with pytest.raises(ValueError, match="exceeds total_amount"):
        process_cash_dividend(
            CashDividendInputs(
                qty_at_record=Decimal("10"),
                amount_per_share=Decimal("2"),  # total = 20
                withholding_tax=Decimal("25"),  # > 20
            )
        )


# D04 — zero qty is legitimate (held nothing on record date)
def test_cash_dividend_zero_qty_returns_zero():
    res = process_cash_dividend(
        CashDividendInputs(
            qty_at_record=Decimal("0"),
            amount_per_share=Decimal("5"),
            withholding_tax=Decimal("0"),
        )
    )
    assert res.total_amount == Decimal("0")
    assert res.net_amount == Decimal("0")
    assert res.realized_pnl_delta == Decimal("0")


# D05 — realized_pnl_delta always equals net_amount
@pytest.mark.parametrize(
    ("qty", "amount", "tax"),
    [
        (Decimal("100"), Decimal("1"), Decimal("0")),
        (Decimal("500"), Decimal("2.5"), Decimal("12.5")),
        (Decimal("1"), Decimal("0.01"), Decimal("0")),
    ],
)
def test_cash_dividend_realized_pnl_delta_equals_net_amount(qty, amount, tax):
    res = process_cash_dividend(
        CashDividendInputs(
            qty_at_record=qty,
            amount_per_share=amount,
            withholding_tax=tax,
        )
    )
    assert res.realized_pnl_delta == res.net_amount


# D-neg — negative inputs rejected
@pytest.mark.parametrize(
    ("qty", "amount", "tax", "field"),
    [
        (Decimal("-1"), Decimal("1"), Decimal("0"), "qty_at_record"),
        (Decimal("10"), Decimal("-0.5"), Decimal("0"), "amount_per_share"),
        (Decimal("10"), Decimal("1"), Decimal("-1"), "withholding_tax"),
    ],
)
def test_cash_dividend_rejects_negative_inputs(qty, amount, tax, field):
    with pytest.raises(ValueError, match=field):
        process_cash_dividend(
            CashDividendInputs(
                qty_at_record=qty,
                amount_per_share=amount,
                withholding_tax=tax,
            )
        )


# ---------------------------------------------------------------------------
# STOCK dividend
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


# D06 — happy path: 1 lot, ratio 0.1
def test_stock_dividend_happy_path():
    lots = [_lot(1, "100", "100", "50")]
    res = process_stock_dividend(
        StockDividendInputs(ratio=Decimal("0.1"), open_lots=lots)
    )
    assert len(res.updated_lots) == 1
    new_lot = res.updated_lots[0]
    assert new_lot.lot_id == 1
    assert new_lot.original_qty == Decimal("110.0")
    assert new_lot.remaining_qty == Decimal("110.0")
    # 50 / 1.1 — keep exact Decimal
    assert new_lot.cost_per_unit == Decimal("50") / Decimal("1.1")
    assert res.total_new_qty_added == Decimal("10.0")


# D07 — per-lot total cost invariant: old_qty*old_cost == new_qty*new_cost
@pytest.mark.parametrize(
    ("ratio_str", "qty_str", "cost_str"),
    [
        ("0.1", "100", "50"),
        ("0.05", "1000", "23.5"),
        ("0.25", "50", "100"),
        ("1", "200", "75"),  # 1:1 配股
    ],
)
def test_stock_dividend_preserves_total_cost_invariant(
    ratio_str, qty_str, cost_str
):
    lots = [_lot(1, qty_str, qty_str, cost_str)]
    res = process_stock_dividend(
        StockDividendInputs(ratio=Decimal(ratio_str), open_lots=lots)
    )
    new_lot = res.updated_lots[0]
    old_total = Decimal(qty_str) * Decimal(cost_str)
    new_total = new_lot.remaining_qty * new_lot.cost_per_unit
    assert new_total == old_total


# D08 — multiple lots all scaled correctly
def test_stock_dividend_multiple_lots():
    lots = [
        _lot(1, "100", "100", "50"),
        _lot(2, "200", "200", "60"),
        _lot(3, "50", "30", "70"),  # partially consumed
    ]
    ratio = Decimal("0.2")
    res = process_stock_dividend(
        StockDividendInputs(ratio=ratio, open_lots=lots)
    )
    assert len(res.updated_lots) == 3
    # Lot 1
    assert res.updated_lots[0].remaining_qty == Decimal("120.0")
    assert res.updated_lots[0].original_qty == Decimal("120.0")
    assert res.updated_lots[0].cost_per_unit == Decimal("50") / Decimal("1.2")
    # Lot 2
    assert res.updated_lots[1].remaining_qty == Decimal("240.0")
    # Lot 3 — original_qty scales too, even though partly consumed
    assert res.updated_lots[2].original_qty == Decimal("60.0")
    assert res.updated_lots[2].remaining_qty == Decimal("36.0")
    # total_new_qty_added = (100 + 200 + 30) * 0.2 = 66
    assert res.total_new_qty_added == Decimal("66.0")


# D09 — ratio 0 is a no-op (lots copied through)
def test_stock_dividend_ratio_zero_noop():
    lots = [
        _lot(1, "100", "100", "50"),
        _lot(2, "200", "150", "60"),
    ]
    res = process_stock_dividend(
        StockDividendInputs(ratio=Decimal("0"), open_lots=lots)
    )
    assert len(res.updated_lots) == 2
    for orig, updated in zip(lots, res.updated_lots, strict=True):
        assert updated.lot_id == orig.lot_id
        assert updated.original_qty == orig.original_qty
        assert updated.remaining_qty == orig.remaining_qty
        assert updated.cost_per_unit == orig.cost_per_unit
        assert updated.is_exhausted == orig.is_exhausted
        # New objects, not aliasing
        assert updated is not orig
    assert res.total_new_qty_added == Decimal("0")


# D10 — negative ratio raises
@pytest.mark.parametrize("ratio", [Decimal("-0.01"), Decimal("-1")])
def test_stock_dividend_negative_ratio_raises(ratio):
    lots = [_lot(1, "100", "100", "50")]
    with pytest.raises(ValueError, match="non-negative"):
        process_stock_dividend(
            StockDividendInputs(ratio=ratio, open_lots=lots)
        )


# D11 — empty lots returns empty result
def test_stock_dividend_empty_lots_returns_empty():
    res = process_stock_dividend(
        StockDividendInputs(ratio=Decimal("0.1"), open_lots=[])
    )
    assert res.updated_lots == []
    assert res.total_new_qty_added == Decimal("0")


# D12 — odd ratio decimal precision preserved (no float coercion)
def test_stock_dividend_decimal_precision_preserved():
    # Use a ratio that would lose precision under float (1/30 = 0.0333...)
    # Pick a Decimal-precision-controlled context.
    ctx_precision_before = getcontext().prec
    try:
        getcontext().prec = 50
        lots = [_lot(1, "300", "300", "99.99")]
        ratio = Decimal("0.0333333333333333333333333333333")
        res = process_stock_dividend(
            StockDividendInputs(ratio=ratio, open_lots=lots)
        )
        new_lot = res.updated_lots[0]

        # Invariant: total cost preserved exactly
        old_total = Decimal("300") * Decimal("99.99")
        new_total = new_lot.remaining_qty * new_lot.cost_per_unit
        assert new_total == old_total

        # remaining_qty == 300 * (1 + ratio)  — exact Decimal arithmetic
        expected_remaining = Decimal("300") * (Decimal("1") + ratio)
        assert new_lot.remaining_qty == expected_remaining

        # total_new_qty_added == 300 * ratio  — exact, no float-style 9.99...e-15
        assert res.total_new_qty_added == Decimal("300") * ratio
    finally:
        getcontext().prec = ctx_precision_before
