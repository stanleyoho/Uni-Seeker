"""Unit tests for FIFO engine — T01–T14."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.trade_journal.fifo_engine import (
    FIFOEngine,
    InsufficientSharesError,
    Lot,
)


def _engine(lots: list[Lot]) -> FIFOEngine:
    return FIFOEngine(open_lots=lots)


# T01: Single lot, full sell
def test_T01_single_lot_full_sell():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    result = engine.process_sell(
        qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert result.realized_pnl == Decimal("5000")
    assert result.updated_lots[0].remaining_qty == Decimal("0")
    assert result.updated_lots[0].is_exhausted is True


# T02: Single lot, partial sell
def test_T02_single_lot_partial_sell():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    result = engine.process_sell(
        qty=Decimal("40"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert result.realized_pnl == Decimal("2000")
    assert result.updated_lots[0].remaining_qty == Decimal("60")
    assert result.updated_lots[0].is_exhausted is False


# T03: Cross two lots, FIFO order
def test_T03_cross_two_lots_fifo():
    engine = _engine(
        [
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
    )
    result = engine.process_sell(
        qty=Decimal("120"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
    )
    # Lot A: 100@100 sold → gain 5000; Lot B: 20@120 sold → gain 600; total=5600
    assert result.realized_pnl == Decimal("5600")
    assert result.updated_lots[0].remaining_qty == Decimal("0")
    assert result.updated_lots[0].is_exhausted is True
    assert result.updated_lots[1].remaining_qty == Decimal("30")
    assert result.updated_lots[1].is_exhausted is False


# T04: Exactly exhaust first lot
def test_T04_exactly_exhaust_first_lot():
    engine = _engine(
        [
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
    )
    result = engine.process_sell(
        qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert result.realized_pnl == Decimal("5000")
    assert result.updated_lots[0].is_exhausted is True
    assert result.updated_lots[1].remaining_qty == Decimal("50")


# T05: Sell at a loss
def test_T05_sell_at_loss():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    result = engine.process_sell(
        qty=Decimal("100"), price=Decimal("80"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert result.realized_pnl == Decimal("-2000")


# T06: Sell exceeds holdings (must raise)
def test_T06_sell_exceeds_holdings():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("50"),
                remaining_qty=Decimal("50"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    with pytest.raises(InsufficientSharesError):
        engine.process_sell(
            qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
        )


# T07: No open position (must raise)
def test_T07_no_open_position():
    engine = _engine([])
    with pytest.raises(InsufficientSharesError):
        engine.process_sell(
            qty=Decimal("100"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
        )


# T08: Fee + tax included in P&L
def test_T08_fee_and_tax_in_pnl():
    # BUY 100@100 fee=100 → cost_per_unit=101; SELL 100@100 fee=100 tax=300
    # proceeds = 10000-100-300=9600; cost = 101*100=10100; realized=-500
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("101"),
            )
        ]
    )
    result = engine.process_sell(
        qty=Decimal("100"), price=Decimal("100"), fee=Decimal("100"), tax=Decimal("300")
    )
    assert result.realized_pnl == Decimal("-500")


# T09: Multiple buys, multiple sells
def test_T09_multiple_buys_multiple_sells():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            ),
            Lot(
                lot_id=2,
                original_qty=Decimal("80"),
                remaining_qty=Decimal("80"),
                cost_per_unit=Decimal("110"),
            ),
            Lot(
                lot_id=3,
                original_qty=Decimal("60"),
                remaining_qty=Decimal("60"),
                cost_per_unit=Decimal("120"),
            ),
        ]
    )
    # Sell 1: 130 shares @150
    # Lot1 fully used (100@100→+5000), Lot2 partial 30@110→+1200; total +6200
    r1 = engine.process_sell(
        qty=Decimal("130"), price=Decimal("150"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert r1.realized_pnl == Decimal("6200")
    # Sell 2: remaining 110 shares @160
    # Lot2 remaining 50@110→+2500, Lot3 60@120→+2400; total +4900
    r2 = engine.process_sell(
        qty=Decimal("110"), price=Decimal("160"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert r2.realized_pnl == Decimal("4900")
    assert r1.realized_pnl + r2.realized_pnl == Decimal("11100")


# T10: 2:1 forward split
def test_T10_forward_split_2for1():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    lots = engine.process_split(ratio=Decimal("2"))
    assert lots[0].remaining_qty == Decimal("200")
    assert lots[0].cost_per_unit == Decimal("50")


# T11: Sell after split uses correct cost
def test_T11_sell_after_split():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("100"),
            )
        ]
    )
    engine.process_split(ratio=Decimal("2"))
    # Now 200 shares @50/share; sell 200@70 → proceeds=14000, cost=10000, realized=+4000
    result = engine.process_sell(
        qty=Decimal("200"), price=Decimal("70"), fee=Decimal("0"), tax=Decimal("0")
    )
    assert result.realized_pnl == Decimal("4000")


# T12: 1:10 reverse split
def test_T12_reverse_split_1for10():
    engine = _engine(
        [
            Lot(
                lot_id=1,
                original_qty=Decimal("100"),
                remaining_qty=Decimal("100"),
                cost_per_unit=Decimal("10"),
            )
        ]
    )
    lots = engine.process_split(ratio=Decimal("0.1"))
    assert lots[0].remaining_qty == Decimal("10")
    assert lots[0].cost_per_unit == Decimal("100")


# T13: Multi-lot split
def test_T13_multi_lot_split():
    engine = _engine(
        [
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
    )
    lots = engine.process_split(ratio=Decimal("2"))
    assert lots[0].remaining_qty == Decimal("200") and lots[0].cost_per_unit == Decimal("50")
    assert lots[1].remaining_qty == Decimal("100") and lots[1].cost_per_unit == Decimal("60")


# T14: Dividend does not touch lots (fifo_engine has no process_dividend)
def test_T14_dividend_no_lot_change():
    lots_before = [
        Lot(
            lot_id=1,
            original_qty=Decimal("100"),
            remaining_qty=Decimal("100"),
            cost_per_unit=Decimal("100"),
        )
    ]
    engine = _engine(lots_before)
    assert not hasattr(engine, "process_dividend"), "FIFOEngine should not handle dividends"
    assert engine._lots[0].remaining_qty == Decimal("100")
