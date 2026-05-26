"""Unit tests for financial_analysis.metrics_calculator.

Pure compute module — no DB / network fixtures needed. Covers:
- _safe_div / _safe_pct private helpers (via compute_metrics)
- deaccumulate (Q1 vs Q2+ branches, point-in-time fields, missing prev keys)
- compute_metrics (full data, missing fields, YoY growth with/without prev_year_income)
"""

from __future__ import annotations

from app.modules.financial_analysis.metrics_calculator import (
    compute_metrics,
    deaccumulate,
)

# ── deaccumulate ───────────────────────────────────────────────────────────


def test_deaccumulate_q1_returns_current_unchanged() -> None:
    """Q1 cumulative IS single-quarter — no subtraction."""
    current = {"Revenue": 1000.0, "OperatingIncome": 200.0}
    result = deaccumulate(current, prev_cum=None, quarter=1)
    assert result == {"Revenue": 1000.0, "OperatingIncome": 200.0}


def test_deaccumulate_q1_with_prev_still_returns_current() -> None:
    """Q1 branch wins even if prev_cum is supplied."""
    result = deaccumulate({"Revenue": 1000.0}, prev_cum={"Revenue": 999.0}, quarter=1)
    assert result == {"Revenue": 1000.0}


def test_deaccumulate_q2_subtracts_flow_keys() -> None:
    """Income / cash-flow keys subtract; YTD - Q1 = Q2 single-quarter."""
    current = {"Revenue": 3000.0, "OperatingIncome": 600.0}
    prev = {"Revenue": 1000.0, "OperatingIncome": 200.0}
    result = deaccumulate(current, prev_cum=prev, quarter=2)
    assert result == {"Revenue": 2000.0, "OperatingIncome": 400.0}


def test_deaccumulate_q3_with_missing_prev_key_treats_as_zero() -> None:
    """Defensive: prev_cum missing a key defaults to 0 (full current = single-quarter)."""
    current = {"Revenue": 5000.0, "GrossProfit": 1500.0}
    prev = {"Revenue": 3000.0}  # no GrossProfit
    result = deaccumulate(current, prev_cum=prev, quarter=3)
    assert result == {"Revenue": 2000.0, "GrossProfit": 1500.0}


def test_deaccumulate_balance_sheet_fields_pit_no_subtraction() -> None:
    """Balance-sheet keys are point-in-time — keep current as-is."""
    current = {
        "TotalAssets": 10000.0,
        "Equity": 6000.0,
        "Revenue": 3000.0,  # flow — should subtract
    }
    prev = {
        "TotalAssets": 9000.0,
        "Equity": 5500.0,
        "Revenue": 1000.0,
    }
    result = deaccumulate(current, prev_cum=prev, quarter=2)
    assert result == {
        "TotalAssets": 10000.0,  # PIT, kept
        "Equity": 6000.0,  # PIT, kept
        "Revenue": 2000.0,  # flow, subtracted
    }


# ── compute_metrics ──────────────────────────────────────────────────────


def test_compute_metrics_full_data_all_ratios() -> None:
    """Happy path — every metric resolves to a non-None numeric."""
    income = {
        "Revenue": 1000.0,
        "GrossProfit": 400.0,
        "OperatingIncome": 200.0,
        "IncomeAfterTaxes": 150.0,
        "EPS": 3.5,
    }
    balance = {
        "TotalAssets": 5000.0,
        "CurrentAssets": 2000.0,
        "CurrentLiabilities": 800.0,
        "TotalLiabilities": 1800.0,
        "Equity": 3200.0,
        "Inventory": 300.0,
    }
    cashflow = {
        "CashFlowsFromOperatingActivities": 250.0,
        "CashFlowsFromInvestingActivities": -100.0,
    }
    m = compute_metrics(income, balance, cashflow)
    assert m["gross_margin"] == 40.0
    assert m["operating_margin"] == 20.0
    assert m["net_margin"] == 15.0
    assert m["roe"] == 4.69  # 150 / 3200 * 100, rounded
    assert m["roa"] == 3.0
    assert m["asset_turnover"] == 0.2
    assert m["debt_to_equity"] == 0.5625
    assert m["current_ratio"] == 2.5
    assert m["quick_ratio"] == (2000 - 300) / 800
    assert m["eps"] == 3.5
    assert m["fcf"] == 150.0  # 250 + (-100)
    assert m["operating_cf_ratio"] == 250 / 150
    # YoY growth missing → None
    assert m["revenue_growth_yoy"] is None
    assert m["eps_growth_yoy"] is None
    assert m["operating_income_growth_yoy"] is None


def test_compute_metrics_missing_income_fields_return_none() -> None:
    """Margins return None when revenue is absent (divide-by-None)."""
    m = compute_metrics(
        income={},
        balance={"TotalAssets": 100.0, "Equity": 50.0},
        cashflow={},
    )
    assert m["gross_margin"] is None
    assert m["operating_margin"] is None
    assert m["net_margin"] is None
    assert m["roe"] is None  # net_income missing
    assert m["fcf"] is None  # both cashflow legs missing


def test_compute_metrics_zero_revenue_returns_none_for_margins() -> None:
    """Divide-by-zero → None (not exception, not infinity)."""
    m = compute_metrics(
        income={"Revenue": 0.0, "GrossProfit": 0.0, "OperatingIncome": 0.0},
        balance={},
        cashflow={},
    )
    assert m["gross_margin"] is None  # 0/0
    assert m["operating_margin"] is None


def test_compute_metrics_quick_ratio_handles_missing_inventory() -> None:
    """When inventory is absent, quick_ratio falls through to None (defensive)."""
    m = compute_metrics(
        income={"Revenue": 1000.0},
        balance={"CurrentAssets": 500.0, "CurrentLiabilities": 200.0},
        # Inventory missing — defaults to 0 via .get(.., 0)
        cashflow={},
    )
    # (500 - 0) / 200 = 2.5
    assert m["quick_ratio"] == 2.5


def test_compute_metrics_yoy_growth_full() -> None:
    """prev_year_income drives YoY revenue / eps / operating growth."""
    income = {"Revenue": 1200.0, "EPS": 4.0, "OperatingIncome": 240.0}
    prev = {"Revenue": 1000.0, "EPS": 3.0, "OperatingIncome": 200.0}
    m = compute_metrics(income, balance={}, cashflow={}, prev_year_income=prev)
    assert m["revenue_growth_yoy"] == 20.0  # +200/1000
    assert m["eps_growth_yoy"] == round((1 / 3) * 100, 2)  # 33.33
    assert m["operating_income_growth_yoy"] == 20.0


def test_compute_metrics_yoy_growth_negative_prev_uses_abs_denominator() -> None:
    """Negative-prev case: denominator uses abs() so growth direction stays
    intuitive when prior period was a loss."""
    income = {"OperatingIncome": -50.0}
    prev = {"OperatingIncome": -100.0}
    m = compute_metrics(income, balance={}, cashflow={}, prev_year_income=prev)
    # (-50 - -100) / abs(-100) * 100 = 50.0
    assert m["operating_income_growth_yoy"] == 50.0


def test_compute_metrics_yoy_growth_missing_prev_field_is_none() -> None:
    """prev_year_income with missing key (e.g. no EPS) → that growth is None."""
    income = {"Revenue": 1200.0, "EPS": 4.0}
    prev = {"Revenue": 1000.0}  # no EPS
    m = compute_metrics(income, balance={}, cashflow={}, prev_year_income=prev)
    assert m["revenue_growth_yoy"] == 20.0
    assert m["eps_growth_yoy"] is None


def test_compute_metrics_yoy_growth_zero_prev_revenue_is_none() -> None:
    """abs(0) is 0 → divide-by-zero → None (not infinity)."""
    income = {"Revenue": 500.0}
    prev = {"Revenue": 0.0}
    m = compute_metrics(income, balance={}, cashflow={}, prev_year_income=prev)
    assert m["revenue_growth_yoy"] is None
