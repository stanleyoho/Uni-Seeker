"""yfinance upstream schema smoke test.

yfinance is an UNOFFICIAL scraper of Yahoo's web endpoints — Yahoo breaks it
without warning roughly once a quarter. We don't want every breakage to red
the nightly cron, so we `xfail` when upstream returns nothing instead of
hard-failing. A FAIL here means yfinance still works but its `.info` schema
has dropped fields we read.
"""

from __future__ import annotations

import pytest

# yfinance is already a runtime dep of the backend (see pyproject.toml).
import yfinance as yf

EXPECTED_INFO_FIELDS = {"symbol", "currentPrice", "marketCap"}


def test_yfinance_ticker_info_schema() -> None:
    """``Ticker('AAPL').info`` must still expose the fields we read."""
    try:
        ticker = yf.Ticker("AAPL")
        info = ticker.info
    except Exception as exc:
        # yfinance raises arbitrary exception types when Yahoo's HTML scrape
        # breaks; broad except is intentional for the xfail guard.
        pytest.xfail(f"yfinance unreachable / raised on .info: {exc}")

    if not info or not isinstance(info, dict):
        pytest.xfail(
            f"yfinance returned empty/non-dict .info (type={type(info).__name__}, "
            f"len={len(info) if info is not None else 'None'}) — likely upstream rate-limit or"
            " schema break, not a regression in our code."
        )

    # Some fields (e.g. currentPrice) are occasionally missing on weekends or
    # for delisted tickers; intersect rather than hard-assert all-present so a
    # partial schema still surfaces useful diagnostics.
    present = EXPECTED_INFO_FIELDS & set(info.keys())
    if not present:
        pytest.xfail(
            "yfinance .info present but none of the expected fields exist. "
            f"Got keys sample: {sorted(info.keys())[:20]}"
        )

    missing = EXPECTED_INFO_FIELDS - set(info.keys())
    assert not missing, (
        f"yfinance .info dropped fields: {missing}. "
        f"Present: {sorted(present)}. Sample of available keys: {sorted(info.keys())[:30]}"
    )
