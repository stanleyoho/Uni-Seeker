"""Unit tests for ``app.modules.institutional.diff``.

Covers all 5 ChangeType classifications, empty-side scenarios, multi-row
aggregation (CUSIP + put_call variants), and Decimal precision.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.institutional.diff import (
    ChangeType,
    HoldingChange,
    compute_diff,
)
from app.modules.institutional.parser import ParsedHolding


def _make_holding(
    cusip: str,
    name: str,
    shares: Decimal,
    value_usd: Decimal,
    put_call: str | None = None,
) -> ParsedHolding:
    """Test factory — sensible defaults for the fields we don't exercise here."""
    return ParsedHolding(
        cusip=cusip,
        name_of_issuer=name,
        value_usd=value_usd,
        shares=shares,
        shares_or_principal_type="SH",
        put_call=put_call,
        investment_discretion="SOLE",
        voting_authority_sole=shares,
        voting_authority_shared=Decimal("0"),
        voting_authority_none=Decimal("0"),
    )


# ───────────────────────── tests ─────────────────────────


def test_diff_all_new() -> None:
    curr = [
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000")),
        _make_holding("BBB222222", "Banana", Decimal("200"), Decimal("20000")),
    ]
    changes = compute_diff([], curr)
    assert len(changes) == 2
    assert all(c.change_type == ChangeType.NEW for c in changes)
    assert all(c.prev_shares is None for c in changes)
    assert all(c.delta_pct is None for c in changes)
    # delta = curr (since prev=0)
    assert changes[0].delta_shares == Decimal("100")
    assert changes[1].delta_value_usd == Decimal("20000")


def test_diff_all_exited() -> None:
    prev = [
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000")),
    ]
    changes = compute_diff(prev, [])
    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.EXITED
    assert changes[0].curr_shares is None
    # Delta is negative — sign convention.
    assert changes[0].delta_shares == Decimal("-100")
    assert changes[0].delta_value_usd == Decimal("-10000")
    assert changes[0].delta_pct is None


def test_diff_increased_classification() -> None:
    prev = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    curr = [_make_holding("AAA111111", "Apple", Decimal("150"), Decimal("15000"))]
    changes = compute_diff(prev, curr)
    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.INCREASED
    assert changes[0].delta_shares == Decimal("50")
    assert changes[0].delta_value_usd == Decimal("5000")
    assert changes[0].delta_pct == Decimal("0.5")  # +50%


def test_diff_decreased_classification() -> None:
    prev = [_make_holding("AAA111111", "Apple", Decimal("200"), Decimal("20000"))]
    curr = [_make_holding("AAA111111", "Apple", Decimal("150"), Decimal("15000"))]
    changes = compute_diff(prev, curr)
    assert changes[0].change_type == ChangeType.DECREASED
    assert changes[0].delta_shares == Decimal("-50")
    assert changes[0].delta_pct == Decimal("-0.25")


def test_diff_unchanged_classification() -> None:
    prev = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    curr = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    changes = compute_diff(prev, curr)
    assert changes[0].change_type == ChangeType.UNCHANGED
    assert changes[0].delta_shares == Decimal("0")
    assert changes[0].delta_pct == Decimal("0")


def test_diff_mixed_changes() -> None:
    prev = [
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000")),
        _make_holding("BBB222222", "Banana", Decimal("200"), Decimal("20000")),
        _make_holding("CCC333333", "Cherry", Decimal("300"), Decimal("30000")),
    ]
    curr = [
        _make_holding("AAA111111", "Apple", Decimal("150"), Decimal("15000")),  # INCREASED
        _make_holding("BBB222222", "Banana", Decimal("200"), Decimal("20000")),  # UNCHANGED
        # Cherry EXITED
        _make_holding("DDD444444", "Date", Decimal("400"), Decimal("40000")),  # NEW
    ]
    changes = compute_diff(prev, curr)
    by_cusip = {c.cusip: c for c in changes}
    assert by_cusip["AAA111111"].change_type == ChangeType.INCREASED
    assert by_cusip["BBB222222"].change_type == ChangeType.UNCHANGED
    assert by_cusip["CCC333333"].change_type == ChangeType.EXITED
    assert by_cusip["DDD444444"].change_type == ChangeType.NEW
    # Output sorted by CUSIP ascending.
    assert [c.cusip for c in changes] == sorted(by_cusip.keys())


def test_diff_handles_empty_prev() -> None:
    """Initial filing scenario — first time we see this filer."""
    curr = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    changes = compute_diff([], curr)
    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.NEW
    assert changes[0].prev_shares is None
    assert changes[0].prev_value_usd is None


def test_diff_handles_empty_curr() -> None:
    """Filer disbanded / filed empty 13F — everything exits."""
    prev = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    changes = compute_diff(prev, [])
    assert len(changes) == 1
    assert changes[0].change_type == ChangeType.EXITED


def test_diff_delta_pct_null_for_new_and_exited() -> None:
    prev = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    curr = [_make_holding("BBB222222", "Banana", Decimal("200"), Decimal("20000"))]
    changes = compute_diff(prev, curr)
    by_cusip = {c.cusip: c for c in changes}
    # AAA exited, BBB new — both must have delta_pct None.
    assert by_cusip["AAA111111"].delta_pct is None
    assert by_cusip["BBB222222"].delta_pct is None


def test_diff_delta_pct_computed_for_inc_dec() -> None:
    prev = [_make_holding("AAA111111", "Apple", Decimal("80"), Decimal("8000"))]
    curr = [_make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"))]
    changes = compute_diff(prev, curr)
    # delta_pct = (100 - 80) / 80 = 0.25
    assert changes[0].delta_pct == Decimal("0.25")


def test_diff_same_cusip_with_put_call_aggregation() -> None:
    """Per spec §7.2: aggregate by CUSIP across put_call variants."""
    prev = [
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"), put_call=None),
        _make_holding("AAA111111", "Apple", Decimal("50"), Decimal("5000"), put_call="CALL"),
    ]
    curr = [
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("10000"), put_call=None),
        _make_holding("AAA111111", "Apple", Decimal("100"), Decimal("12000"), put_call="CALL"),
    ]
    changes = compute_diff(prev, curr)
    assert len(changes) == 1
    c = changes[0]
    # Aggregated shares: prev=150, curr=200 → +50
    assert c.prev_shares == Decimal("150")
    assert c.curr_shares == Decimal("200")
    assert c.delta_shares == Decimal("50")
    # Aggregated value: prev=15000, curr=22000 → +7000
    assert c.delta_value_usd == Decimal("7000")
    assert c.change_type == ChangeType.INCREASED


def test_diff_decimal_precision_preserved() -> None:
    """No float drift — sums of fractional shares remain exact."""
    prev = [
        _make_holding(
            "AAA111111",
            "Apple",
            Decimal("0.0001"),
            Decimal("0.0001"),
        )
    ]
    curr = [
        _make_holding(
            "AAA111111",
            "Apple",
            Decimal("0.0002"),
            Decimal("0.0003"),
        )
    ]
    changes = compute_diff(prev, curr)
    c = changes[0]
    assert c.delta_shares == Decimal("0.0001")
    # Exact subtraction — no 0.00029999... artefact.
    assert c.delta_value_usd == Decimal("0.0002")
    # delta_pct = 0.0001 / 0.0001 = 1 exactly
    assert c.delta_pct == Decimal("1")
