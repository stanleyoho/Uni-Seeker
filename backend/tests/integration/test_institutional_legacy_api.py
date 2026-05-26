"""Integration tests for the legacy /api/v1/institutional/{symbol}
FinMind 三大法人 endpoint + the in-module _aggregate helper."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from httpx import AsyncClient

from app.api.v1.institutional.legacy import _aggregate


# ── _aggregate ─────────────────────────────────────────────────────────────


def test_aggregate_empty_input() -> None:
    assert _aggregate([]) == []


def test_aggregate_unknown_category_skipped() -> None:
    raw = [{"date": "2026-05-01", "name": "Foreign_VIP", "buy": 100, "sell": 50}]
    assert _aggregate(raw) == []


def test_aggregate_categorizes_and_nets() -> None:
    raw = [
        {"date": "2026-05-01", "name": "Foreign_Investor", "buy": 1000, "sell": 600},
        {"date": "2026-05-01", "name": "Investment_Trust", "buy": 400, "sell": 200},
        {"date": "2026-05-01", "name": "Dealer_self", "buy": 100, "sell": 150},
    ]
    out = _aggregate(raw)
    assert len(out) == 1
    rec = out[0]
    assert rec.foreign_net == 400
    assert rec.trust_net == 200
    assert rec.dealer_net == -50
    assert rec.total_net == 550


def test_aggregate_dealer_self_and_hedging_merged() -> None:
    raw = [
        {"date": "2026-05-01", "name": "Dealer_self", "buy": 100, "sell": 50},
        {"date": "2026-05-01", "name": "Dealer_Hedging", "buy": 200, "sell": 100},
    ]
    out = _aggregate(raw)
    assert out[0].dealer_buy == 300
    assert out[0].dealer_net == 150


def test_aggregate_sorted_by_date() -> None:
    raw = [
        {"date": "2026-05-03", "name": "Foreign_Investor", "buy": 30, "sell": 10},
        {"date": "2026-05-01", "name": "Foreign_Investor", "buy": 10, "sell": 5},
        {"date": "2026-05-02", "name": "Foreign_Investor", "buy": 20, "sell": 8},
    ]
    out = _aggregate(raw)
    assert [r.date for r in out] == ["2026-05-01", "2026-05-02", "2026-05-03"]


# ── GET /institutional/{symbol} ────────────────────────────────────────────


async def test_endpoint_returns_empty_data_when_provider_empty(client: AsyncClient) -> None:
    with patch("app.api.v1.institutional.legacy.FinMindInstitutionalProvider") as p:
        p.return_value.fetch_institutional = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/institutional/2330?start_date=2026-05-01&end_date=2026-05-31")
    assert resp.status_code == 200
    assert resp.json() == {"symbol": "2330", "data": []}


async def test_endpoint_aggregates_provider_records(client: AsyncClient) -> None:
    """End-to-end through real _aggregate."""
    raw = [
        {"date": "2026-05-01", "name": "Foreign_Investor", "buy": 1000, "sell": 600},
        {"date": "2026-05-01", "name": "Investment_Trust", "buy": 400, "sell": 200},
    ]
    with patch("app.api.v1.institutional.legacy.FinMindInstitutionalProvider") as p:
        p.return_value.fetch_institutional = AsyncMock(return_value=raw)
        resp = await client.get(
            "/api/v1/institutional/2330.TW?start_date=2026-05-01&end_date=2026-05-31"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "2330.TW"
    assert len(data["data"]) == 1
    rec = data["data"][0]
    assert rec["foreign_net"] == 400
    assert rec["trust_net"] == 200


async def test_endpoint_502_on_provider_exception(client: AsyncClient) -> None:
    """Provider raise → 502 FinMind error."""
    with patch("app.api.v1.institutional.legacy.FinMindInstitutionalProvider") as p:
        p.return_value.fetch_institutional = AsyncMock(
            side_effect=RuntimeError("upstream timeout")
        )
        resp = await client.get(
            "/api/v1/institutional/2330?start_date=2026-05-01&end_date=2026-05-31"
        )
    assert resp.status_code == 502
    assert "FinMind error" in resp.json()["message"]


async def test_endpoint_strips_tw_suffix_for_provider_call(client: AsyncClient) -> None:
    """Symbol `2330.TW` → provider called with `2330` (suffix stripped)."""
    with patch("app.api.v1.institutional.legacy.FinMindInstitutionalProvider") as p:
        p.return_value.fetch_institutional = AsyncMock(return_value=[])
        await client.get(
            "/api/v1/institutional/2330.TW?start_date=2026-05-01&end_date=2026-05-31"
        )
    assert p.return_value.fetch_institutional.await_args.kwargs["stock_id"] == "2330"
