"""Unit tests for `app.modules.portfolio.wash_sale_detector`.

Phase 5 wash-sale detection (Round 11). Coverage:

  Detection
    W01 no_loss_no_wash_sale
    W02 loss_no_replacement_no_wash_sale
    W03 loss_replacement_within_30_days_after_triggers
    W04 loss_replacement_within_30_days_before_triggers
    W05 loss_replacement_outside_30_days_no_wash_sale
    W06 loss_replacement_different_symbol_no_wash_sale
    W07 partial_match_when_replacement_qty_less
    W08 disallowed_loss_calculation_proportional
    W09 replacement_remaining_qty_tracking_across_losses
    W10 exact_30_days_inclusive
    W11 exact_31_days_excluded

  Application
    W12 apply_resets_gain_loss_to_zero
    W13 apply_marks_is_wash_sale_true
    W14 apply_preserves_matches_without_wash_sale
    W15 form_8949_csv_includes_W_code (via projected helper)
    W16 form_8949_csv_adjustment_column_shows_disallowed_loss

  Boundary helper
    W17 date_within_window_inclusive_bounds
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.modules.portfolio.tax_report import (
    TaxLotMatch,
    compute_matched_pairs,
)
from app.modules.portfolio.wash_sale_detector import (
    apply_wash_sale_adjustments,
    date_within_window,
    detect_wash_sales,
)

# ── builders (mirror test_tax_report._buy / _sell + trade-log row) ────


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


def _trade(tid, action, sym, td, qty, price="100", market="US_NASDAQ"):
    """Trade-log row in the shape `detect_wash_sales` consumes."""
    return {
        "id": tid,
        "action": action,
        "symbol": sym,
        "market": market,
        "trade_date": td,
        "qty": Decimal(qty),
        "price": Decimal(price),
    }


# ── detection ────────────────────────────────────────────────────────


def test_W01_no_loss_no_wash_sale():
    """All matches are gains → detector emits zero adjustments."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "100")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "150")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert result.adjustments == []
    assert result.total_disallowed_loss == Decimal("0")


def test_W02_loss_no_replacement_no_wash_sale():
    """Loss SELL with no nearby BUY → no wash sale."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    assert matches[0].gain_loss < Decimal("0")  # confirmed loss
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert result.adjustments == []


def test_W03_loss_replacement_within_30_days_after_triggers():
    """Loss on day 0, replacement BUY on day +20 → wash sale."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 21), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert len(result.adjustments) == 1
    adj = result.adjustments[0]
    assert adj.symbol == "AAPL"
    assert adj.replacement_trade_id == 3
    assert adj.matched_qty == Decimal("100")
    assert adj.disallowed_loss == Decimal("5000")  # 150*100 - 100*100
    assert result.total_disallowed_loss == Decimal("5000")


def test_W04_loss_replacement_within_30_days_before_triggers():
    """Replacement BUY on day -10 (before the loss SELL) → wash sale.

    §1091 covers replacements BEFORE the sale too."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 5, 22), "50"),
    ]
    result = detect_wash_sales(trades, matches)
    assert len(result.adjustments) == 1
    adj = result.adjustments[0]
    assert adj.replacement_trade_id == 3
    assert adj.matched_qty == Decimal("50")
    # disallowed = 5000 * 50/100 = 2500
    assert adj.disallowed_loss == Decimal("2500")


def test_W05_loss_replacement_outside_30_days_no_wash_sale():
    """Replacement BUY 45 days after sale → outside window, no wash sale."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 7, 16), "100"),  # +45 days
    ]
    result = detect_wash_sales(trades, matches)
    assert result.adjustments == []


def test_W06_loss_replacement_different_symbol_no_wash_sale():
    """Replacement BUY in MSFT, loss is on AAPL → not substantially identical."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "MSFT", date(2024, 6, 10), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert result.adjustments == []


def test_W07_partial_match_when_replacement_qty_less():
    """100-share loss + 30-share replacement → 30% disallowed."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 15), "30"),
    ]
    result = detect_wash_sales(trades, matches)
    assert len(result.adjustments) == 1
    adj = result.adjustments[0]
    assert adj.matched_qty == Decimal("30")
    # disallowed = 5000 * 30/100 = 1500
    assert adj.disallowed_loss == Decimal("1500")


def test_W08_disallowed_loss_calculation_proportional():
    """50-share replacement against 100-share loss = exactly 50% disallow."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "200", fee="0")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "180")]
    matches = compute_matched_pairs(buys, sells)
    # Verify loss: (180 - 200) * 100 = -2000
    assert matches[0].gain_loss == Decimal("-2000")
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 5), "50"),
    ]
    result = detect_wash_sales(trades, matches)
    assert len(result.adjustments) == 1
    # 2000 * 50/100 = 1000
    assert result.adjustments[0].disallowed_loss == Decimal("1000")


def test_W09_replacement_remaining_qty_tracking_across_losses():
    """Two loss SELLs compete for the same 50-share replacement BUY.

    Earliest sale gets first claim on the limited replacement supply."""
    buys = [
        _buy(1, "AAPL", date(2023, 1, 1), "80", "200"),
        _buy(2, "AAPL", date(2023, 6, 1), "80", "200"),
    ]
    sells = [
        _sell(3, "AAPL", date(2024, 6, 1), "80", "150"),
        _sell(4, "AAPL", date(2024, 6, 10), "80", "150"),
    ]
    matches = compute_matched_pairs(buys, sells)
    # Both losses: (150-200)*80 = -4000 each.
    assert all(m.gain_loss == Decimal("-4000") for m in matches)

    trades = [
        _trade(1, "BUY", "AAPL", date(2023, 1, 1), "80"),
        _trade(2, "BUY", "AAPL", date(2023, 6, 1), "80"),
        _trade(3, "SELL", "AAPL", date(2024, 6, 1), "80"),
        _trade(4, "SELL", "AAPL", date(2024, 6, 10), "80"),
        _trade(5, "BUY", "AAPL", date(2024, 6, 5), "50"),  # single replacement
    ]
    result = detect_wash_sales(trades, matches)
    # First-loss (sale 2024-06-01) consumes all 50 of the replacement.
    # Second-loss (sale 2024-06-10) finds zero remaining.
    assert len(result.adjustments) == 1
    adj = result.adjustments[0]
    assert adj.sale_date == date(2024, 6, 1)
    assert adj.matched_qty == Decimal("50")
    # 4000 * 50/80 = 2500
    assert adj.disallowed_loss == Decimal("2500")


def test_W10_exact_30_days_inclusive():
    """Replacement exactly 30 days after sale → IN window (wash sale)."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 1) + timedelta(days=30), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert len(result.adjustments) == 1


def test_W11_exact_31_days_excluded():
    """Replacement on day +31 → OUT of window (no wash sale)."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 1) + timedelta(days=31), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    assert result.adjustments == []


# ── application ──────────────────────────────────────────────────────


def test_W12_apply_resets_gain_loss_to_zero():
    """Disallowed loss equals the full magnitude → gain_loss becomes 0."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 21), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    adjusted = apply_wash_sale_adjustments(matches, result.adjustments)
    assert len(adjusted) == 1
    assert adjusted[0].gain_loss == Decimal("0")
    assert adjusted[0].wash_sale_disallowed_loss == Decimal("5000")


def test_W13_apply_marks_is_wash_sale_true():
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    assert matches[0].is_wash_sale is False
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 21), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    adjusted = apply_wash_sale_adjustments(matches, result.adjustments)
    assert adjusted[0].is_wash_sale is True


def test_W14_apply_preserves_matches_without_wash_sale():
    """A gain match is passed through unchanged when no adjustment applies."""
    buys = [
        _buy(1, "AAPL", date(2024, 1, 1), "100", "150"),  # → loss leg
        _buy(2, "MSFT", date(2024, 1, 1), "100", "100"),  # → gain leg
    ]
    sells = [
        _sell(3, "AAPL", date(2024, 6, 1), "100", "100"),
        _sell(4, "MSFT", date(2024, 6, 1), "100", "200"),
    ]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "BUY", "MSFT", date(2024, 1, 1), "100"),
        _trade(3, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(4, "SELL", "MSFT", date(2024, 6, 1), "100"),
        _trade(5, "BUY", "AAPL", date(2024, 6, 5), "100"),  # AAPL replacement
    ]
    result = detect_wash_sales(trades, matches)
    adjusted = apply_wash_sale_adjustments(matches, result.adjustments)
    matches_by_sym = {m.symbol: m for m in adjusted}
    # AAPL row was a wash sale.
    assert matches_by_sym["AAPL"].is_wash_sale is True
    # MSFT row untouched.
    assert matches_by_sym["MSFT"].is_wash_sale is False
    assert matches_by_sym["MSFT"].gain_loss == Decimal("10000")


def _project_csv(match: TaxLotMatch) -> dict[str, str]:
    """Project a TaxLotMatch into the Form 8949 column dict the service emits.

    Mirrors the service-layer CSV builder for unit testing without
    booting FastAPI / DB.
    """
    code = "W" if match.is_wash_sale else ""
    adjustment = (
        str(match.wash_sale_disallowed_loss) if match.is_wash_sale else ""
    )
    return {
        "Code": code,
        "Adjustment": adjustment,
        "Gain/Loss": str(match.gain_loss),
        "Wash Sale": "true" if match.is_wash_sale else "false",
    }


def test_W15_form_8949_csv_includes_W_code():
    """Wash-sale row carries Code='W' in the Form 8949 projection."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 21), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    adjusted = apply_wash_sale_adjustments(matches, result.adjustments)
    row = _project_csv(adjusted[0])
    assert row["Code"] == "W"
    assert row["Wash Sale"] == "true"


def test_W16_form_8949_csv_adjustment_column_shows_disallowed_loss():
    """Adjustment column equals the disallowed-loss magnitude."""
    buys = [_buy(1, "AAPL", date(2024, 1, 1), "100", "150")]
    sells = [_sell(2, "AAPL", date(2024, 6, 1), "100", "100")]
    matches = compute_matched_pairs(buys, sells)
    trades = [
        _trade(1, "BUY", "AAPL", date(2024, 1, 1), "100"),
        _trade(2, "SELL", "AAPL", date(2024, 6, 1), "100"),
        _trade(3, "BUY", "AAPL", date(2024, 6, 21), "100"),
    ]
    result = detect_wash_sales(trades, matches)
    adjusted = apply_wash_sale_adjustments(matches, result.adjustments)
    row = _project_csv(adjusted[0])
    assert Decimal(row["Adjustment"]) == Decimal("5000")
    assert Decimal(row["Gain/Loss"]) == Decimal("0")


# ── boundary helper ──────────────────────────────────────────────────


def test_W17_date_within_window_inclusive_bounds():
    """The boundary helper is the source-of-truth for window inclusivity."""
    d = date(2024, 6, 1)
    assert date_within_window(d, d) is True
    assert date_within_window(d, d + timedelta(days=30)) is True
    assert date_within_window(d, d - timedelta(days=30)) is True
    assert date_within_window(d, d + timedelta(days=31)) is False
    assert date_within_window(d, d - timedelta(days=31)) is False
