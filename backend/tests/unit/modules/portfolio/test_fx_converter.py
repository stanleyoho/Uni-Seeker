"""Unit tests for `fx_converter` — pure FX math, no I/O.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11
      (FX support).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.portfolio.fx_converter import (
    FxRateMissing,
    convert,
    convert_dict,
    convert_to_base,
)

# ── convert() ─────────────────────────────────────────────────────────────


def test_convert_applies_rate():
    """`amount * rate` returned as Decimal."""
    assert convert(Decimal("100"), Decimal("30")) == Decimal("3000")


def test_convert_none_amount_passthrough():
    """`amount is None` → None (no rate applied)."""
    assert convert(None, Decimal("30")) is None


def test_convert_none_rate_raises():
    """`rate is None` is a programmer error."""
    with pytest.raises(ValueError):
        convert(Decimal("100"), None)  # type: ignore[arg-type]


# ── convert_to_base() ─────────────────────────────────────────────────────


def test_convert_to_base_sums_mixed_currencies():
    """100 USD * 30 + 5000 JPY * 0.2 = 3000 + 1000 = 4000 TWD."""
    amounts = {
        "USD": Decimal("100"),
        "JPY": Decimal("5000"),
    }
    rates = {
        "USD": Decimal("30"),
        "JPY": Decimal("0.2"),
    }
    assert convert_to_base(amounts, rates, "TWD") == Decimal("4000")


def test_convert_to_base_base_currency_no_rate_needed():
    """Amount in base currency adds as-is (rate=1 implicit)."""
    amounts = {
        "TWD": Decimal("1000"),
        "USD": Decimal("10"),
    }
    rates = {"USD": Decimal("30")}  # No TWD entry needed.
    assert convert_to_base(amounts, rates, "TWD") == Decimal("1300")


def test_convert_to_base_empty_returns_zero():
    """Empty input → Decimal('0')."""
    assert convert_to_base({}, {}, "TWD") == Decimal("0")


def test_convert_to_base_missing_rate_raises():
    """Currency not in rates and not equal to base → FxRateMissing."""
    amounts = {"EUR": Decimal("50")}
    rates = {"USD": Decimal("30")}  # No EUR rate.
    with pytest.raises(FxRateMissing) as excinfo:
        convert_to_base(amounts, rates, "TWD")
    assert excinfo.value.currency == "EUR"
    assert excinfo.value.base == "TWD"


def test_convert_to_base_case_insensitive():
    """Lower-case currency codes are normalised."""
    amounts = {"usd": Decimal("100"), "twd": Decimal("50")}
    rates = {"USD": Decimal("30")}
    assert convert_to_base(amounts, rates, "twd") == Decimal("3050")


# ── convert_dict() ────────────────────────────────────────────────────────


def test_convert_dict_returns_per_currency_in_base():
    """Each currency contributes its base-equivalent value to output dict."""
    amounts = {
        "USD": Decimal("100"),
        "JPY": Decimal("5000"),
        "TWD": Decimal("200"),
    }
    rates = {
        "USD": Decimal("30"),
        "JPY": Decimal("0.2"),
    }
    out = convert_dict(amounts, rates, "TWD")
    assert out == {
        "USD": Decimal("3000"),
        "JPY": Decimal("1000"),
        "TWD": Decimal("200"),
    }


def test_convert_dict_missing_rate_raises():
    """Non-base currency without rate → FxRateMissing."""
    with pytest.raises(FxRateMissing):
        convert_dict({"GBP": Decimal("10")}, {}, "TWD")
