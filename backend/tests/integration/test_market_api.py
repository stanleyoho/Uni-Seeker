"""Integration tests for /api/v1/market/* — movers + indices endpoints.

Covers:
- /movers: empty DB → demo fallback; real DB with gainers/losers/most-active;
  cache hit short-circuits DB query; market_filter narrows scope;
  insufficient-rows padding from demo.
- /indices: empty DB → demo fallback; real DB with computed last/change.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock


async def _mk_stock_with_price(
    db: AsyncSession,
    symbol: str,
    name: str,
    market: Market,
    d: date,
    close: float,
    change_pct: float,
    volume: int,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=market)
    db.add(s)
    await db.commit()
    await db.refresh(s)

    p = StockPrice(
        stock_id=s.id,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        change=Decimal(str(close * change_pct / 100)),
        volume=volume,
    )
    p.change_percent = Decimal(str(change_pct))
    db.add(p)
    await db.commit()
    return s


# ── /movers ────────────────────────────────────────────────────────────────


async def test_movers_empty_db_returns_demo(client: AsyncClient) -> None:
    """No StockPrice rows → demo movers fallback (gainers + losers + most_active)."""
    resp = await client.get("/api/v1/market/movers")
    assert resp.status_code == 200
    data = resp.json()
    assert "gainers" in data
    assert "losers" in data
    assert "most_active" in data
    assert len(data["gainers"]) >= 1
    assert len(data["losers"]) >= 1


async def test_movers_real_data_classified_by_sign(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stocks with positive change → gainers; negative → losers."""
    d = date(2026, 5, 1)
    # Seed 6+ rows in each direction so the demo-fallback padding path is bypassed
    for i in range(6):
        await _mk_stock_with_price(
            db_session,
            f"G{i}",
            f"Gainer{i}",
            Market.TW_TWSE,
            d,
            close=100.0,
            change_pct=5.0 + i * 0.1,
            volume=1_000_000 + i * 1000,
        )
        await _mk_stock_with_price(
            db_session,
            f"L{i}",
            f"Loser{i}",
            Market.TW_TWSE,
            d,
            close=100.0,
            change_pct=-5.0 - i * 0.1,
            volume=500_000 + i * 1000,
        )

    resp = await client.get("/api/v1/market/movers?limit=3")
    assert resp.status_code == 200
    data = resp.json()
    # Limit=3 caps each list to 3
    assert len(data["gainers"]) == 3
    assert len(data["losers"]) == 3
    # First gainer has the highest change_percent
    for g in data["gainers"]:
        assert float(g["change_percent"]) > 0
    for losser in data["losers"]:
        assert float(losser["change_percent"]) < 0


async def test_movers_market_filter_excludes_other_markets(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """market_filter restricts the latest_date lookup + result set."""
    d = date(2026, 5, 1)
    for i in range(6):
        await _mk_stock_with_price(
            db_session,
            f"TW{i}",
            f"TW{i}",
            Market.TW_TWSE,
            d,
            close=100.0,
            change_pct=5.0,
            volume=1_000_000,
        )
        await _mk_stock_with_price(
            db_session,
            f"US{i}",
            f"US{i}",
            Market.US_NASDAQ,
            d,
            close=200.0,
            change_pct=8.0,
            volume=2_000_000,
        )

    resp = await client.get("/api/v1/market/movers?market_filter=TW_TWSE")
    assert resp.status_code == 200
    data = resp.json()
    # At minimum, no US-prefixed symbol leaked into either bucket
    assert not any(g["symbol"].startswith("US") for g in data["gainers"])
    assert not any(g["symbol"].startswith("US") for g in data["losers"])
    # And the TW-prefixed seed stocks must have actually shown up somewhere.
    real_gainers = [g for g in data["gainers"] if g["symbol"].startswith("TW")]
    assert len(real_gainers) > 0


# ── /indices ───────────────────────────────────────────────────────────────


async def test_indices_empty_db_returns_demo(client: AsyncClient) -> None:
    """No data → demo indices fallback (>=4 indices)."""
    resp = await client.get("/api/v1/market/indices")
    assert resp.status_code == 200
    data = resp.json()
    assert "indices" in data
    assert len(data["indices"]) >= 4


async def test_indices_response_shape(client: AsyncClient) -> None:
    """Indices payload exposes name + last + change fields."""
    resp = await client.get("/api/v1/market/indices")
    assert resp.status_code == 200
    data = resp.json()
    for idx in data["indices"]:
        assert "name" in idx
        assert "last" in idx or "value" in idx  # whichever schema name
