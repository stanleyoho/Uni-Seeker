"""FinMind upstream schema smoke test.

Hits the public ``TaiwanStockInfo`` dataset (no auth required) and asserts
that the response shape still contains the fields our code reads. We do NOT
assert specific values — TWSE adds/removes listings daily, and that's
expected. We only guard against silent field renames / structural drift.

If this test fails in the nightly workflow, FinMind likely shipped a
breaking change and our `app.modules.finmind.*` providers need updating.
"""

from __future__ import annotations

import httpx
import pytest

from tests.external_smoke.conftest import SMOKE_HTTP_TIMEOUT

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
# Field set our code actually reads. See
# `app/modules/sync_manager/tasks/stock_info.py` — note the market column is
# `type` (values "OTC" / "twse"), NOT `market_type` as some FinMind docs
# state. If FinMind ever renames `type` → `market_type` we want to know
# BEFORE the next stock_info sync silently writes all stocks as TWSE.
EXPECTED_FIELDS = {"stock_id", "stock_name", "industry_category", "type"}


def test_finmind_taiwan_stock_info_schema() -> None:
    """TaiwanStockInfo must still expose the four fields our providers read.

    Public dataset — no token needed. We only sample the first record's keys
    to keep the assertion cheap.
    """
    try:
        response = httpx.get(
            FINMIND_URL,
            params={"dataset": "TaiwanStockInfo"},
            timeout=SMOKE_HTTP_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        pytest.fail(f"FinMind timed out after {SMOKE_HTTP_TIMEOUT}s: {exc}")
    except httpx.HTTPError as exc:
        pytest.fail(f"FinMind unreachable: {exc}")

    assert response.status_code == 200, (
        f"FinMind returned {response.status_code}: {response.text[:200]}"
    )

    body = response.json()
    assert body.get("msg") == "success", (
        f"FinMind msg != 'success' (got {body.get('msg')!r}). Body sample: {body!r}"[:300]
    )

    records = body.get("data", [])
    assert isinstance(records, list), f"FinMind .data is not a list: {type(records).__name__}"
    assert len(records) > 0, "FinMind returned zero TaiwanStockInfo records"

    sample = records[0]
    assert isinstance(sample, dict), f"FinMind record is not a dict: {type(sample).__name__}"

    missing = EXPECTED_FIELDS - set(sample.keys())
    assert not missing, (
        f"FinMind TaiwanStockInfo dropped fields: {missing}. "
        f"Sample record keys: {sorted(sample.keys())}"
    )
