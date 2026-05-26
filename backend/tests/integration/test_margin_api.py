"""Integration tests for /api/v1/margin/* — TWSE margin trading API.

Mocks TWSEMarginProvider.fetch_margin_data to avoid network access.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient

from app.modules.margin.base import MarginData


def _md(
    symbol: str = "2330",
    margin_balance: int = 1000,
    margin_limit: int = 5000,
    short_balance: int = 200,
    short_limit: int = 1000,
) -> MarginData:
    return MarginData(
        symbol=symbol,
        name="TestCo",
        date=date(2026, 5, 1),
        margin_buy=100,
        margin_sell=50,
        margin_cash_repay=10,
        margin_balance_prev=950,
        margin_balance=margin_balance,
        margin_limit=margin_limit,
        short_buy=20,
        short_sell=10,
        short_cash_repay=5,
        short_balance_prev=190,
        short_balance=short_balance,
        short_limit=short_limit,
        offset=15,
    )


# ── POST /margin/update ───────────────────────────────────────────────────


async def test_update_returns_fetched_count(client: AsyncClient) -> None:
    fake = [_md("2330"), _md("0050"), _md("2317")]
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.post("/api/v1/margin/update")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fetched"] == 3
    assert data["saved"] == 3


# ── GET /margin/ ──────────────────────────────────────────────────────────


async def test_list_calculates_usage_percentages(client: AsyncClient) -> None:
    """margin_usage_pct = margin_balance / margin_limit * 100, rounded 2dp."""
    fake = [_md("2330", margin_balance=2500, margin_limit=5000)]  # 50%
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.get("/api/v1/margin/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    row = data["data"][0]
    assert row["symbol"] == "2330"
    assert row["margin_usage_pct"] == 50.0
    assert row["short_usage_pct"] == 20.0  # 200/1000*100
    # ms_ratio = 200/2500*100 = 8.0
    assert row["margin_short_ratio"] == 8.0


async def test_list_zero_limit_returns_zero_pct(client: AsyncClient) -> None:
    """Guard against divide-by-zero when limit is 0."""
    fake = [_md("2330", margin_limit=0, short_limit=0, margin_balance=0)]
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.get("/api/v1/margin/")
    row = resp.json()["data"][0]
    assert row["margin_usage_pct"] == 0
    assert row["short_usage_pct"] == 0
    assert row["margin_short_ratio"] == 0


async def test_list_empty_response(client: AsyncClient) -> None:
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/margin/")
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "total": 0}


# ── GET /margin/{symbol} ──────────────────────────────────────────────────


async def test_get_by_symbol_exact_match(client: AsyncClient) -> None:
    fake = [_md("2330"), _md("0050")]
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.get("/api/v1/margin/2330")
    assert resp.status_code == 200
    assert resp.json()["symbol"] == "2330"


async def test_get_by_symbol_strips_dot_tw_suffix(client: AsyncClient) -> None:
    """`2330.TW` → matches `2330` via .replace cleanup."""
    fake = [_md("2330")]
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.get("/api/v1/margin/2330.TW")
    assert resp.status_code == 200


async def test_get_by_symbol_404_when_missing(client: AsyncClient) -> None:
    fake = [_md("2330")]
    with patch("app.api.v1.margin.TWSEMarginProvider") as prov_cls:
        prov_cls.return_value.fetch_margin_data = AsyncMock(return_value=fake)
        resp = await client.get("/api/v1/margin/UNKNOWN")
    assert resp.status_code == 404
