"""Integration tests for /api/v1/tw-institutional endpoints."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.tw_institutional import TwInstitutionalNet
from app.modules.sync_manager.tasks.tw_institutional import _aggregate_rows

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


# ── _aggregate_rows ──────────────────────────────────────────────────────


def test_aggregate_rows_empty() -> None:
    assert _aggregate_rows([]) == {}


def test_aggregate_rows_skips_unknown_category() -> None:
    raw = [{"date": "2026-05-29", "name": "Foreign_VIP", "buy": 1, "sell": 2}]
    assert _aggregate_rows(raw) == {}


def test_aggregate_rows_merges_dealer_sub_categories() -> None:
    raw = [
        {"date": "2026-05-29", "name": "Dealer_self", "buy": 100, "sell": 50},
        {"date": "2026-05-29", "name": "Dealer_Hedging", "buy": 200, "sell": 100},
    ]
    out = _aggregate_rows(raw)
    assert out[date(2026, 5, 29)]["dealer_net"] == 150


def test_aggregate_rows_nets_three_categories() -> None:
    raw = [
        {"date": "2026-05-29", "name": "Foreign_Investor", "buy": 1000, "sell": 600},
        {"date": "2026-05-29", "name": "Investment_Trust", "buy": 300, "sell": 100},
        {"date": "2026-05-29", "name": "Dealer_self", "buy": 50, "sell": 80},
    ]
    out = _aggregate_rows(raw)
    bucket = out[date(2026, 5, 29)]
    assert bucket["foreign_net"] == 400
    assert bucket["trust_net"] == 200
    assert bucket["dealer_net"] == -30


def test_aggregate_rows_invalid_date_skipped() -> None:
    raw = [{"date": "not-a-date", "name": "Foreign_Investor", "buy": 1, "sell": 1}]
    assert _aggregate_rows(raw) == {}


# ── GET /tw-institutional/top-net ────────────────────────────────────────


async def _seed(db: "AsyncSession") -> dict[str, Stock]:
    """Seed 3 stocks with tw_institutional_net rows for 2026-05-29.

    Returns a {symbol → Stock} map for assertion lookups.
    """
    from app.models.enums import Market

    stocks = {
        "2330": Stock(
            symbol="2330", name="台積電", market=Market.TW_TWSE,
        ),
        "2454": Stock(
            symbol="2454", name="聯發科", market=Market.TW_TWSE,
        ),
        "2317": Stock(
            symbol="2317", name="鴻海", market=Market.TW_TWSE,
        ),
    }
    for s in stocks.values():
        db.add(s)
    await db.commit()
    for s in stocks.values():
        await db.refresh(s)

    d = date(2026, 5, 29)

    # foreign: 2330 buys big, 2454 mid, 2317 sells.
    rows = [
        TwInstitutionalNet(
            stock_id=stocks["2330"].id, date=d,
            foreign_net=10_000_000, trust_net=1_000_000,
            dealer_net=500_000, total_net=11_500_000,
        ),
        TwInstitutionalNet(
            stock_id=stocks["2454"].id, date=d,
            foreign_net=5_000_000, trust_net=2_000_000,
            dealer_net=-100_000, total_net=6_900_000,
        ),
        TwInstitutionalNet(
            stock_id=stocks["2317"].id, date=d,
            foreign_net=-3_000_000, trust_net=-500_000,
            dealer_net=200_000, total_net=-3_300_000,
        ),
    ]
    for r in rows:
        db.add(r)

    db.add(
        StockPrice(
            stock_id=stocks["2330"].id, date=d,
            open=Decimal("1240"), high=Decimal("1250"),
            low=Decimal("1235"), close=Decimal("1245"),
            volume=12_345_000,
        )
    )
    await db.commit()
    return stocks


async def test_top_net_empty_db_returns_clean_message(client: "AsyncClient") -> None:
    """Empty DB must not 500 — return clean empty payload + message."""
    resp = await client.get(
        "/api/v1/tw-institutional/top-net?date=2026-05-29&kind=foreign"
        "&direction=buy&limit=5"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["kind"] == "foreign"
    assert body["direction"] == "buy"
    assert body["message"] is not None


async def test_top_net_foreign_buy_orders_descending(
    client: "AsyncClient",
    db_session: "AsyncSession",
) -> None:
    await _seed(db_session)

    resp = await client.get(
        "/api/v1/tw-institutional/top-net?date=2026-05-29&kind=foreign"
        "&direction=buy&limit=5"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Two stocks have positive foreign_net; 2317 (negative) is excluded.
    assert [row["symbol"] for row in data] == ["2330", "2454"]
    assert data[0]["net_amount"] == 10_000_000
    # 2330 has a price row → price/change_percent populated.
    assert data[0]["price"] is not None


async def test_top_net_dealer_sell_orders_most_negative_first(
    client: "AsyncClient",
    db_session: "AsyncSession",
) -> None:
    await _seed(db_session)

    resp = await client.get(
        "/api/v1/tw-institutional/top-net?date=2026-05-29&kind=foreign"
        "&direction=sell&limit=5"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Only 2317 has negative foreign_net.
    assert [row["symbol"] for row in data] == ["2317"]
    assert data[0]["net_amount"] == -3_000_000


async def test_top_net_invalid_kind_rejected(client: "AsyncClient") -> None:
    resp = await client.get(
        "/api/v1/tw-institutional/top-net?kind=bogus&direction=buy&limit=5"
    )
    assert resp.status_code == 400


async def test_top_net_invalid_direction_rejected(client: "AsyncClient") -> None:
    resp = await client.get(
        "/api/v1/tw-institutional/top-net?kind=foreign&direction=middle&limit=5"
    )
    assert resp.status_code == 400


async def test_top_net_falls_back_to_latest_date_when_requested_missing(
    client: "AsyncClient",
    db_session: "AsyncSession",
) -> None:
    """Requested 2026-05-30 has no data; we should still surface the
    leaderboard from the latest available date (2026-05-29)."""
    await _seed(db_session)

    resp = await client.get(
        "/api/v1/tw-institutional/top-net?date=2026-05-30&kind=foreign"
        "&direction=buy&limit=5"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-05-29"
    assert len(body["data"]) == 2


# ── GET /tw-institutional/symbol/{symbol} ────────────────────────────────


async def test_symbol_history_returns_404_for_unknown_stock(
    client: "AsyncClient",
) -> None:
    resp = await client.get("/api/v1/tw-institutional/symbol/9999?days=30")
    assert resp.status_code == 404


async def test_symbol_history_returns_recent_rows(
    client: "AsyncClient",
    db_session: "AsyncSession",
) -> None:
    stocks = await _seed(db_session)
    _ = stocks  # silence unused
    resp = await client.get(
        "/api/v1/tw-institutional/symbol/2330?days=365"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "2330"
    assert body["name"] == "台積電"
    assert len(body["data"]) == 1
    assert body["data"][0]["foreign_net"] == 10_000_000
    # Sanity: returned ISO date round-trips.
    assert datetime.fromisoformat(body["data"][0]["date"])
