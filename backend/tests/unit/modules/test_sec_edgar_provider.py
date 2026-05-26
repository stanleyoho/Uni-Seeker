"""Unit tests for ``app.modules.financial_analysis.sec_edgar_provider``.

The provider talks to SEC EDGAR over HTTP and parses XBRL companyfacts
JSON into our internal ``FinancialData`` shape. All network I/O is
mocked at the ``httpx.AsyncClient`` boundary; no real requests fire.

Coverage targets the missing lines in the 19.8 % baseline:
  * ``_get_cik`` happy path + cache hit + ticker-not-found
  * ``_fetch_facts`` happy path
  * ``_extract_statements`` for flow / instant kinds, with annual +
    quarterly frames, first-wins fallback, missing-key skip
  * ``fetch_financials`` orchestration
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.financial_analysis.sec_edgar_provider import (
    SECEdgarFinancialProvider,
    _cik_cache,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _ticker_payload() -> dict[str, dict[str, Any]]:
    """Mimic the SEC company_tickers.json payload."""
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp."},
    }


def _facts_payload() -> dict[str, Any]:
    """Mimic a SEC EDGAR companyfacts JSON payload.

    Covers each statement kind with one or two periods to exercise:
      * quarterly + annual frame matching
      * first-wins fallback chains (Revenues → fallback path)
      * missing-key skip (BalanceSheet has no "Assets" entry)
    """
    return {
        "facts": {
            "us-gaap": {
                # Revenue: only the fallback "Revenues" present —
                # exercises the chain.
                "Revenues": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024Q1", "end": "2024-03-31", "val": 100_000.0},
                            {"frame": "CY2024", "end": "2024-12-31", "val": 400_000.0},
                            # Frame that does NOT match any regex (TTM-style) -> skipped.
                            {"frame": "CY2024Q1Q4", "end": "2024-12-31", "val": 999.0},
                            # Missing end-date -> skipped.
                            {"frame": "CY2024Q2", "end": "", "val": 1.0},
                        ]
                    }
                },
                "CostOfRevenue": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024Q1", "end": "2024-03-31", "val": 40_000.0},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024Q1", "end": "2024-03-31", "val": 20_000.0},
                        ]
                    }
                },
                # Balance sheet
                "AssetsCurrent": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024Q1I", "end": "2024-03-31", "val": 500_000.0},
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024I", "end": "2024-12-31", "val": 1_000_000.0},
                        ]
                    }
                },
                # Cash flow
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"frame": "CY2024Q1", "end": "2024-03-31", "val": 25_000.0},
                        ]
                    }
                },
                # Field with empty units -> skipped path.
                "DepreciationDepletionAndAmortization": {"units": {}},
            }
        }
    }


def _async_response(json_data: dict[str, Any]) -> MagicMock:
    """Mock for the awaited ``client.get(...)`` response object."""
    resp = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    resp.raise_for_status = MagicMock(return_value=None)
    return resp


def _async_client_ctx(get_return: dict[str, Any]) -> MagicMock:
    """Build a MagicMock that simulates ``async with httpx.AsyncClient(...) as c``.

    ``c.get(...)`` is awaited and returns the canned response.
    """
    resp = _async_response(get_return)

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


@pytest.fixture(autouse=True)
def _reset_cik_cache():
    """Ensure the module-level CIK cache is empty between tests."""
    _cik_cache.clear()
    yield
    _cik_cache.clear()


# ─────────────────────────────────────────────────────────────────────
# _get_cik
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_cik_first_call_fetches_and_caches() -> None:
    provider = SECEdgarFinancialProvider()
    ctx = _async_client_ctx(_ticker_payload())

    with patch("httpx.AsyncClient", return_value=ctx):
        cik = await provider._get_cik("AAPL")

    # CIK is zero-padded to 10 digits.
    assert cik == "0000320193"
    # All tickers from the payload land in the cache.
    assert _cik_cache["AAPL"] == "0000320193"
    assert _cik_cache["MSFT"] == "0000789019"


@pytest.mark.asyncio
async def test_get_cik_uses_cache_when_present() -> None:
    """A cached ticker must NOT trigger another HTTP fetch."""
    _cik_cache["AAPL"] = "0000320193"

    provider = SECEdgarFinancialProvider()

    # If we accidentally hit httpx the call will explode (no mock).
    with patch("httpx.AsyncClient", side_effect=AssertionError("should not be called")):
        cik = await provider._get_cik("AAPL")
    assert cik == "0000320193"

    # Lower-case input also satisfies the cache (uppercased internally).
    with patch("httpx.AsyncClient", side_effect=AssertionError("should not be called")):
        cik = await provider._get_cik("aapl")
    assert cik == "0000320193"


@pytest.mark.asyncio
async def test_get_cik_unknown_ticker_raises_value_error() -> None:
    provider = SECEdgarFinancialProvider()
    ctx = _async_client_ctx(_ticker_payload())

    with (
        patch("httpx.AsyncClient", return_value=ctx),
        pytest.raises(ValueError, match="not found"),
    ):
        await provider._get_cik("NOPE")


# ─────────────────────────────────────────────────────────────────────
# _fetch_facts
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_facts_returns_parsed_json() -> None:
    provider = SECEdgarFinancialProvider()
    facts = _facts_payload()
    ctx = _async_client_ctx(facts)

    with patch("httpx.AsyncClient", return_value=ctx):
        result = await provider._fetch_facts("0000320193")

    assert result == facts


# ─────────────────────────────────────────────────────────────────────
# _extract_statements — direct unit tests
# ─────────────────────────────────────────────────────────────────────


def test_extract_statements_flow_picks_quarterly_and_annual() -> None:
    provider = SECEdgarFinancialProvider()
    gaap = _facts_payload()["facts"]["us-gaap"]

    income = provider._extract_statements(
        gaap,
        [
            ("Revenues", "Total Revenue"),
            ("CostOfRevenue", "Cost Of Revenue"),
            ("NetIncomeLoss", "Net Income"),
        ],
        "flow",
    )

    # We expect at most 2 periods (CY2024Q1 + CY2024 annual).
    assert len(income) == 2
    by_period = {s.period: s for s in income}
    # 2024-12-31 is the annual frame, only Revenue lands there (400k).
    annual = by_period["2024-12-31"]
    assert annual.period_type == "annual"
    assert annual.data["Total Revenue"] == 400_000.0
    # 2024-03-31 is quarterly, has all three fields.
    quarterly = by_period["2024-03-31"]
    assert quarterly.period_type == "quarterly"
    assert quarterly.data["Total Revenue"] == 100_000.0
    assert quarterly.data["Cost Of Revenue"] == 40_000.0
    assert quarterly.data["Net Income"] == 20_000.0


def test_extract_statements_instant_kind_uses_balance_regex() -> None:
    provider = SECEdgarFinancialProvider()
    gaap = _facts_payload()["facts"]["us-gaap"]

    balance = provider._extract_statements(
        gaap,
        [
            ("AssetsCurrent", "Current Assets"),
            ("StockholdersEquity", "Stockholders Equity"),
        ],
        "instant",
    )

    # Two distinct periods — one quarterly (CY2024Q1I), one annual (CY2024I).
    periods = {s.period: s for s in balance}
    assert "2024-03-31" in periods
    assert "2024-12-31" in periods
    assert periods["2024-03-31"].period_type == "quarterly"
    assert periods["2024-12-31"].period_type == "annual"
    assert periods["2024-03-31"].data["Current Assets"] == 500_000.0
    assert periods["2024-12-31"].data["Stockholders Equity"] == 1_000_000.0


def test_extract_statements_skips_missing_concepts_and_empty_units() -> None:
    """Concepts absent from gaap, or with empty units, are quietly skipped."""
    provider = SECEdgarFinancialProvider()
    gaap = _facts_payload()["facts"]["us-gaap"]

    out = provider._extract_statements(
        gaap,
        [
            ("DoesNotExist", "Phantom"),  # absent → skipped
            ("DepreciationDepletionAndAmortization", "D&A"),  # units={} → skipped
            ("NetIncomeLoss", "Net Income"),  # present
        ],
        "flow",
    )

    # Only Net Income makes it into the statement set.
    assert len(out) == 1
    assert out[0].data == {"Net Income": 20_000.0}


def test_extract_statements_first_wins_fallback() -> None:
    """When the same field_name appears twice (fallback chain), keep the first.

    We pass two concepts that both map to "Total Revenue"; the first
    (``Revenues``) is the only one present so it must populate the field.
    A *second* concept exists in the gaap dict but its value must NOT
    overwrite the first.
    """
    provider = SECEdgarFinancialProvider()
    gaap: dict[str, Any] = {
        "Revenues": {
            "units": {
                "USD": [
                    {"frame": "CY2024Q1", "end": "2024-03-31", "val": 111.0},
                ]
            }
        },
        # Same period, alternate concept that maps to the same field.
        "RevenueFromContractWithCustomerExcludingAssessedTax": {
            "units": {
                "USD": [
                    {"frame": "CY2024Q1", "end": "2024-03-31", "val": 999.0},
                ]
            }
        },
    }
    out = provider._extract_statements(
        gaap,
        [
            ("Revenues", "Total Revenue"),
            ("RevenueFromContractWithCustomerExcludingAssessedTax", "Total Revenue"),
        ],
        "flow",
    )
    assert len(out) == 1
    # First concept won; the alternate did not overwrite.
    assert out[0].data["Total Revenue"] == 111.0


def test_extract_statements_empty_returns_empty_list() -> None:
    provider = SECEdgarFinancialProvider()
    assert provider._extract_statements({}, [("X", "Y")], "flow") == []


def test_extract_statements_sorts_descending_and_caps_at_20() -> None:
    """Most-recent-first ordering and 20-period cap from the source."""
    provider = SECEdgarFinancialProvider()
    # Build 25 distinct quarterly periods.
    entries = []
    for year in range(2000, 2025):
        entries.append(
            {"frame": f"CY{year}Q1", "end": f"{year}-03-31", "val": float(year)}
        )
    gaap = {"NetIncomeLoss": {"units": {"USD": entries}}}

    out = provider._extract_statements(
        gaap,
        [("NetIncomeLoss", "Net Income")],
        "flow",
    )
    assert len(out) == 20
    # Sorted desc, so the most recent is first.
    assert out[0].period == "2024-03-31"
    assert out[-1].period == "2005-03-31"


# ─────────────────────────────────────────────────────────────────────
# fetch_financials — end-to-end orchestration
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_financials_end_to_end() -> None:
    """Wire ``_get_cik`` + ``_fetch_facts`` through ``fetch_financials``."""
    provider = SECEdgarFinancialProvider()

    # First call (in _get_cik): tickers JSON.
    # Second call (in _fetch_facts): companyfacts JSON.
    # We return different payloads per call by setting side_effect on .get.
    tickers_resp = _async_response(_ticker_payload())
    facts_resp = _async_response(_facts_payload())

    # Each `async with httpx.AsyncClient(...) as client` produces its own
    # client mock; .get is awaited once per context.
    def _make_ctx(resp: MagicMock) -> MagicMock:
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    ctxs = [_make_ctx(tickers_resp), _make_ctx(facts_resp)]
    with patch("httpx.AsyncClient", side_effect=ctxs):
        data = await provider.fetch_financials("AAPL")

    assert data.symbol == "AAPL"
    assert data.currency == "USD"
    # All three statement kinds populated from the mocked facts.
    assert len(data.income_statements) >= 1
    assert len(data.balance_sheets) >= 1
    assert len(data.cash_flows) >= 1
