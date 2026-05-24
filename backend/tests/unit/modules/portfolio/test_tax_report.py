"""Unit tests for `app.modules.portfolio.tax_report`.

Phase 4+ tax export (Round 10). Coverage:

  T01 classify_holding_period — same-day  → SHORT / 0 days
  T02 classify_holding_period — 1 day off → SHORT
  T03 classify_holding_period — 365 days  → SHORT (boundary)
  T04 classify_holding_period — 366 days  → LONG (boundary)
  T05 classify_holding_period — leap year crossover (Feb 29 → Mar 1)
  T06 compute_matched_pairs — single BUY/SELL FIFO
  T07 compute_matched_pairs — SELL across three BUYs (chain)
  T08 compute_matched_pairs — short + long term mixed within one SELL
  T09 compute_matched_pairs — fee allocated proportionally to matched qty
  T10 compute_matched_pairs — proceeds net of SELL fee + tax
  T11 compute_matched_pairs — insufficient BUY history raises
  T12 compute_matched_pairs — Decimal precision preserved (no float)
  T13 compute_matched_pairs — multi-symbol isolation (queues per symbol)
  T14 summarize_by_year — year split + gain/loss separation
  T15 summarize_by_year — empty matches returns empty dict
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.portfolio.tax_report import (
    classify_holding_period,
    compute_matched_pairs,
    summarize_by_year,
)

# ── classify_holding_period ───────────────────────────────────────────


def test_T01_same_day_is_short_term():
    term, days = classify_holding_period(date(2025, 5, 19), date(2025, 5, 19))
    assert term == "SHORT"
    assert days == 0


def test_T02_one_day_apart_is_short_term():
    term, days = classify_holding_period(date(2025, 5, 19), date(2025, 5, 20))
    assert term == "SHORT"
    assert days == 1


def test_T03_exactly_365_days_is_short_term():
    """IRS rule: > 365 days is LONG. Exactly 365 is still SHORT."""
    term, days = classify_holding_period(date(2024, 5, 19), date(2025, 5, 19))
    assert days == 365
    assert term == "SHORT"


def test_T04_three_sixty_six_days_is_long_term():
    """One day past the boundary → LONG term."""
    term, days = classify_holding_period(date(2024, 5, 19), date(2025, 5, 20))
    assert days == 366
    assert term == "LONG"


def test_T05_leap_year_crossover():
    """Buying 2024-02-29 and selling 2025-03-01: 366 days → LONG."""
    term, days = classify_holding_period(date(2024, 2, 29), date(2025, 3, 1))
    assert days == 366
    assert term == "LONG"


# ── compute_matched_pairs ─────────────────────────────────────────────


def _buy(trade_id, sym, acq, qty, price, fee="0", market="US_NASDAQ"):
    return {
        "trade_id": trade_id,
        "symbol": sym,
        "market": market,
        "acquisition_date": acq,
        "qty": Decimal(qty),
        "cost_per_unit": Decimal(price),
        "total_fee": Decimal(fee),
    }


def _sell(trade_id, sym, sold, qty, price, fee="0", tax="0", market="US_NASDAQ"):
    return {
        "trade_id": trade_id,
        "symbol": sym,
        "market": market,
        "sale_date": sold,
        "qty": Decimal(qty),
        "price_per_unit": Decimal(price),
        "total_fee": Decimal(fee),
        "total_tax": Decimal(tax),
    }


def test_T06_single_buy_sell_fifo_match():
    buys = [_buy(1, "AAPL", date(2024, 1, 5), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 7, 1), "100", "200")]

    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 1
    m = matches[0]
    assert m.symbol == "AAPL"
    assert m.market == "US_NASDAQ"
    assert m.quantity == Decimal("100")
    assert m.acquisition_date == date(2024, 1, 5)
    assert m.sale_date == date(2024, 7, 1)
    assert m.cost_basis == Decimal("15000")     # 150 * 100
    assert m.proceeds == Decimal("20000")        # 200 * 100
    assert m.gain_loss == Decimal("5000")
    assert m.term == "SHORT"
    assert m.holding_period_days == 178
    assert m.is_wash_sale is False


def test_T07_sell_across_three_buys_chain_match():
    """One SELL of 150 shares consumes BUY1 (50), BUY2 (50), BUY3 (50)
    — emits three Form 8949 rows."""
    buys = [
        _buy(1, "TSLA", date(2024, 1, 1), "50", "100"),
        _buy(2, "TSLA", date(2024, 2, 1), "50", "120"),
        _buy(3, "TSLA", date(2024, 3, 1), "50", "150"),
    ]
    sells = [_sell(4, "TSLA", date(2024, 6, 1), "150", "200")]

    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 3
    # FIFO order: BUY1 first, then BUY2, then BUY3.
    assert matches[0].acquisition_date == date(2024, 1, 1)
    assert matches[1].acquisition_date == date(2024, 2, 1)
    assert matches[2].acquisition_date == date(2024, 3, 1)
    # Cost basis per row:
    assert matches[0].cost_basis == Decimal("5000")   # 100 * 50
    assert matches[1].cost_basis == Decimal("6000")   # 120 * 50
    assert matches[2].cost_basis == Decimal("7500")   # 150 * 50
    # Proceeds is split evenly (no fee): 200 * 50 per row.
    for m in matches:
        assert m.proceeds == Decimal("10000")
        assert m.quantity == Decimal("50")
    # Net gain summed:
    total_gain = sum((m.gain_loss for m in matches), Decimal("0"))
    assert total_gain == Decimal("11500")             # 30000 - 18500


def test_T08_short_and_long_term_mix_in_one_sell():
    """BUY1 from 2023-01 (long), BUY2 from 2024-05 (short). One SELL
    of 100 in 2024-08 consumes both and emits both terms."""
    buys = [
        _buy(1, "MSFT", date(2023, 1, 10), "60", "200"),
        _buy(2, "MSFT", date(2024, 5, 1), "40", "300"),
    ]
    sells = [_sell(3, "MSFT", date(2024, 8, 15), "100", "400")]
    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 2
    long_match = matches[0]
    short_match = matches[1]
    # First match comes from the older BUY1 → LONG (2023-01 → 2024-08
    # is > 365 days).
    assert long_match.term == "LONG"
    assert long_match.quantity == Decimal("60")
    # Second match consumes BUY2 → SHORT (~3 months).
    assert short_match.term == "SHORT"
    assert short_match.quantity == Decimal("40")


def test_T09_buy_fee_allocated_proportionally():
    """BUY of 100 shares with $50 fee. A SELL of 40 shares should
    allocate 40/100 = 0.4 of the BUY fee into cost basis."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "100", fee="50")]
    sells = [_sell(2, "AAPL", date(2024, 2, 1), "40", "120")]
    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 1
    # cost_basis = 100 * 40 + 50 * (40/100) = 4000 + 20 = 4020
    assert matches[0].cost_basis == Decimal("4020")


def test_T10_proceeds_net_of_sell_fee_and_tax():
    """SELL of 100 @ 150, fee 20, tax 30 → proceeds = 15000 - 50 = 14950."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "100")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "150",
                   fee="20", tax="30")]
    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 1
    assert matches[0].proceeds == Decimal("14950")
    assert matches[0].gain_loss == Decimal("4950")  # 14950 - 10000


def test_T11_insufficient_buy_history_raises():
    """SELL > total BUY → ValueError surfaced upward."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "50", "100")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "150")]
    with pytest.raises(ValueError, match="insufficient BUY history"):
        compute_matched_pairs(buys, sells)


def test_T12_decimal_precision_preserved():
    """Eight-decimal qty + price round-trips exactly."""
    buys = [_buy(1, "BTC", date(2024, 1, 1), "0.12345678", "30000.55",
                 market="US_NYSE")]
    sells = [_sell(2, "BTC", date(2024, 6, 1), "0.12345678", "45000.99",
                   market="US_NYSE")]
    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 1
    # cost = 30000.55 * 0.12345678 = 3703.7041389...
    assert matches[0].cost_basis == Decimal("30000.55") * Decimal("0.12345678")
    assert matches[0].proceeds == Decimal("45000.99") * Decimal("0.12345678")
    # gain_loss == proceeds - cost_basis exactly.
    assert (
        matches[0].gain_loss
        == matches[0].proceeds - matches[0].cost_basis
    )


def test_T13_multi_symbol_isolation():
    """Two symbols mixed — FIFO queues stay independent per (symbol, market)."""
    buys = [
        _buy(1, "A", date(2024, 1, 1), "10", "100"),
        _buy(2, "B", date(2024, 1, 2), "10", "200"),
    ]
    sells = [
        _sell(3, "A", date(2024, 3, 1), "10", "150"),
        _sell(4, "B", date(2024, 3, 2), "10", "250"),
    ]
    matches = compute_matched_pairs(buys, sells)
    assert len(matches) == 2
    matches.sort(key=lambda m: m.symbol)
    a, b = matches
    assert a.symbol == "A" and a.gain_loss == Decimal("500")
    assert b.symbol == "B" and b.gain_loss == Decimal("500")


# ── summarize_by_year ─────────────────────────────────────────────────


def test_T14_summarize_by_year_split_and_signs():
    """Three matches across two years: per-year + gain/loss columns."""
    buys = [
        _buy(1, "A", date(2023, 1, 1), "10", "100"),  # → LONG (sold 2024-06)
        _buy(2, "A", date(2024, 1, 1), "10", "200"),  # → SHORT (sold 2024-06)
        _buy(3, "B", date(2025, 1, 1), "10", "300"),  # → SHORT loss (sold 2025-06)
    ]
    sells = [
        _sell(4, "A", date(2024, 6, 1), "20", "150"),  # one SELL consumes 1+2
        _sell(5, "B", date(2025, 6, 1), "10", "250"),  # loss
    ]
    matches = compute_matched_pairs(buys, sells)
    summary = summarize_by_year(matches)
    assert set(summary) == {2024, 2025}

    s2024 = summary[2024]
    # 2024 contains both legs of the A SELL:
    #   LONG  : 10 * (150 - 100) = +500
    #   SHORT : 10 * (150 - 200) = -500
    assert s2024.long_term_gain == Decimal("500")
    assert s2024.long_term_loss == Decimal("0")
    assert s2024.short_term_gain == Decimal("0")
    assert s2024.short_term_loss == Decimal("-500")
    assert s2024.total_net == Decimal("0")
    assert s2024.total_matches == 2

    s2025 = summary[2025]
    # 2025: a single SHORT loss.
    assert s2025.short_term_loss == Decimal("-500")
    assert s2025.short_term_gain == Decimal("0")
    assert s2025.long_term_gain == Decimal("0")
    assert s2025.total_net == Decimal("-500")
    assert s2025.total_matches == 1


def test_T15_summarize_empty_returns_empty_dict():
    assert summarize_by_year([]) == {}
