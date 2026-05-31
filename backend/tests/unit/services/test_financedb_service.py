"""Tests for the FinanceDatabase symbol-taxonomy service.

These tests **hit the real FinanceDatabase parquet file** (no network,
just a local pip-installed dataset). They're fast (~200ms for the first
test that warms the cache; ~µs for everything after) and deterministic
because FinanceDatabase ships with its data baked in.

Tests are guarded by ``pytest.importorskip`` so a CI runner that hasn't
installed the ``financedatabase`` wheel yet (transitional state right
after this PR lands) doesn't red the whole suite.
"""

from __future__ import annotations

import pytest

pytest.importorskip("financedatabase")

from app.services.symbol_taxonomy import (
    enrich_stock,
    get_us_equity_universe,
    reset_cache,
)

# FinanceDatabase lazy-downloads its dataset from raw.githubusercontent.com
# on first call (~15 MB). The download is cached in the user's home
# directory by FinanceDatabase itself, so subsequent runs are O(1), but
# the first run on a cold CI runner takes ~10s. Mark the module as
# ``slow`` so individual developers can ``pytest -m "not slow"`` while
# debugging.
pytestmark = pytest.mark.slow


# Module-scope cache reset: do it once, not per-test. With a per-test
# reset every test re-downloads the parquet (~10s × 7 = wasted minute).
@pytest.fixture(scope="module", autouse=True)
def _reset_once() -> None:
    reset_cache()


def test_universe_has_thousands_of_us_symbols() -> None:
    """Sanity: the universe should be large (~14-15k symbols) — if
    something filters it down to a handful, the heatmap will break."""
    universe = get_us_equity_universe()
    assert len(universe) > 5_000, f"universe too small: {len(universe)}"
    # Spot check a handful of household-name large caps that should
    # never disappear from FinanceDatabase.
    symbols = {r.symbol for r in universe}
    for must_have in ("AAPL", "MSFT", "NVDA", "JPM", "JNJ"):
        assert must_have in symbols, f"missing well-known symbol: {must_have}"


def test_enrich_stock_finds_apple() -> None:
    """Known-good symbol returns sector + industry."""
    rec = enrich_stock("AAPL")
    assert rec is not None
    assert rec.symbol == "AAPL"
    # FinanceDatabase tags AAPL as Information Technology — guard
    # against silent taxonomy shifts.
    assert rec.sector == "Information Technology"
    assert rec.industry  # any non-empty string is fine — the exact
    # GICS Level-2 may shift over time (Electronic Equipment vs Tech
    # Hardware) so don't pin it.
    assert rec.country == "United States"


def test_enrich_stock_unknown_returns_none() -> None:
    """Symbols not in the universe return None (caller falls back)."""
    assert enrich_stock("ZZZ_NOT_A_REAL_SYMBOL") is None
    assert enrich_stock("") is None


def test_enrich_stock_normalizes_case() -> None:
    """Symbols are case-insensitive — FinanceDatabase stores them
    uppercase, callers might pass lowercase."""
    upper = enrich_stock("AAPL")
    lower = enrich_stock("aapl")
    assert upper is not None
    assert lower is not None
    assert upper.symbol == lower.symbol


def test_universe_sorted_by_symbol() -> None:
    """Stable iteration matters for the backfill script's logs and any
    test that diffs the output."""
    universe = get_us_equity_universe()
    symbols = [r.symbol for r in universe]
    assert symbols == sorted(symbols)


def test_universe_records_are_us_listed() -> None:
    """Every record in the universe must be country='United States'."""
    universe = get_us_equity_universe()
    for rec in universe[:50]:  # spot-check first 50 — full scan is ~15k
        assert rec.country == "United States"


def test_universe_no_duplicate_symbols() -> None:
    """Dedup must be effective — same symbol must not appear twice."""
    universe = get_us_equity_universe()
    symbols = [r.symbol for r in universe]
    assert len(symbols) == len(set(symbols)), "duplicate symbols in universe"
