"""Unit tests for `price_estimator.utils.ValuationUtils`.

Pure-compute coverage for `calculate_cagr` + `clean_outliers`.
Async DB methods (`get_dynamic_growth_rate`, `estimate_wacc`) tested
via integration suite (separate file).
"""

from __future__ import annotations

from app.modules.price_estimator.utils import ValuationUtils

# ── calculate_cagr ───────────────────────────────────────────────────────


def test_calculate_cagr_empty_returns_default() -> None:
    assert ValuationUtils.calculate_cagr([]) == 0.05


def test_calculate_cagr_single_value_returns_default() -> None:
    assert ValuationUtils.calculate_cagr([10.0]) == 0.05


def test_calculate_cagr_zero_start_returns_default() -> None:
    """Guards against divide-by-zero / negative growth bias."""
    assert ValuationUtils.calculate_cagr([0.0, 5.0, 10.0]) == 0.05


def test_calculate_cagr_negative_start_returns_default() -> None:
    assert ValuationUtils.calculate_cagr([-1.0, 5.0]) == 0.05


def test_calculate_cagr_negative_end_returns_default() -> None:
    assert ValuationUtils.calculate_cagr([10.0, -5.0]) == 0.05


def test_calculate_cagr_growth_within_bounds() -> None:
    """4 quarterly values (1 year) doubling EPS → ~100% CAGR → clamped to 15%."""
    result = ValuationUtils.calculate_cagr([1.0, 1.2, 1.5, 2.0])
    assert result == 0.15  # clamped upper bound


def test_calculate_cagr_modest_growth_unclamped() -> None:
    """Mild 5% per-year growth — 4 quarters: 1.0 → 1.05."""
    result = ValuationUtils.calculate_cagr([1.0, 1.012, 1.025, 1.05])
    # n=1 year → cagr = 1.05^(1/1) - 1 = 0.05
    assert 0.02 <= result <= 0.15


def test_calculate_cagr_shrinking_clamped_to_floor() -> None:
    """Declining EPS → negative CAGR → clamped to 0.02 floor."""
    result = ValuationUtils.calculate_cagr([10.0, 8.0, 6.0, 4.0])
    assert result == 0.02


# ── clean_outliers ───────────────────────────────────────────────────────


def test_clean_outliers_short_list_returned_as_is() -> None:
    """Fewer than 4 values → IQR not meaningful, return unchanged."""
    assert ValuationUtils.clean_outliers([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]
    assert ValuationUtils.clean_outliers([]) == []


def test_clean_outliers_removes_extreme_high() -> None:
    values = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 1000.0]
    cleaned = ValuationUtils.clean_outliers(values)
    assert 1000.0 not in cleaned
    assert 10.0 in cleaned
    assert 17.0 in cleaned


def test_clean_outliers_removes_extreme_low() -> None:
    values = [-9999.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]
    cleaned = ValuationUtils.clean_outliers(values)
    assert -9999.0 not in cleaned


def test_clean_outliers_keeps_all_when_uniform() -> None:
    """No values outside Q1-1.5*IQR..Q3+1.5*IQR → keep all."""
    values = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    cleaned = ValuationUtils.clean_outliers(values)
    assert cleaned == values
