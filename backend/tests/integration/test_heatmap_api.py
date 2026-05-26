"""Integration tests for /api/v1/heatmap/sectors endpoint.

Covers:
- Empty DB → falls back to _demo_heatmap (hardcoded fallback dataset)
- DB with grouped industries → real sector aggregation
- market_filter Query param
- top_n Query param caps stocks per sector
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock


async def _mk_industry(db: AsyncSession, name: str) -> Industry:
    ind = Industry(name=name)
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


async def _mk_stock(
    db: AsyncSession,
    symbol: str,
    name: str,
    industry_id: int | None,
    market: Market = Market.TW_TWSE,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=market)
    s.industry_id = industry_id
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def _mk_price(
    db: AsyncSession,
    stock_id: int,
    d: date,
    close: float,
    change_pct: float,
    volume: int = 100_000,
) -> StockPrice:
    p = StockPrice(
        stock_id=stock_id,
        date=d,
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        change=Decimal("0"),
        volume=volume,
    )
    p.change_percent = Decimal(str(change_pct))
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def test_heatmap_empty_db_returns_demo_fallback(client: AsyncClient) -> None:
    """No StockPrice rows → /sectors returns the hardcoded demo dataset
    (multiple TW industries with rep stocks)."""
    resp = await client.get("/api/v1/heatmap/sectors")
    assert resp.status_code == 200
    data = resp.json()
    assert "sectors" in data
    assert "date" in data
    # Demo dataset has at least 5 sectors per MIN_HEATMAP_SECTORS
    assert len(data["sectors"]) >= 5
    # Demo dataset always includes the semiconductor sector
    semi_present = any("Semiconductor" in s["industry"] for s in data["sectors"])
    assert semi_present


async def test_heatmap_real_data_groups_by_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Seed 2 industries x 2 stocks each x 1 day → response groups them."""
    semi = await _mk_industry(db_session, "Semiconductor")
    finance = await _mk_industry(db_session, "Finance")

    s1 = await _mk_stock(db_session, "2330", "TSMC", semi.id)
    s2 = await _mk_stock(db_session, "2303", "UMC", semi.id)
    s3 = await _mk_stock(db_session, "2882", "Cathay", finance.id)

    d = date(2026, 5, 1)
    await _mk_price(db_session, s1.id, d, close=895.0, change_pct=4.0, volume=1000)
    await _mk_price(db_session, s2.id, d, close=52.0, change_pct=2.5, volume=2000)
    await _mk_price(db_session, s3.id, d, close=42.0, change_pct=-0.5, volume=500)

    resp = await client.get("/api/v1/heatmap/sectors")
    assert resp.status_code == 200
    data = resp.json()

    sectors = {s["industry"]: s for s in data["sectors"]}
    assert "Semiconductor" in sectors
    assert "Finance" in sectors

    semi_sector = sectors["Semiconductor"]
    assert semi_sector["stock_count"] == 2
    # Decimal serializes as string per CLAUDE.md convention.
    assert float(semi_sector["avg_change_percent"]) == round((4.0 + 2.5) / 2, 2)
    assert semi_sector["total_volume"] == 3000


async def test_heatmap_top_n_caps_stocks_per_sector(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """top_n=2 → at most 2 stocks per sector, sorted by abs(change_percent) DESC."""
    semi = await _mk_industry(db_session, "Semiconductor")
    d = date(2026, 5, 1)
    # 4 stocks with varying change_percent
    for i, (sym, chg) in enumerate([("A", 1.0), ("B", 5.0), ("C", -3.0), ("D", 0.5)]):
        s = await _mk_stock(db_session, sym, sym, semi.id)
        await _mk_price(db_session, s.id, d, close=100.0, change_pct=chg)

    resp = await client.get("/api/v1/heatmap/sectors?top_n=2")
    assert resp.status_code == 200
    data = resp.json()
    sectors = {s["industry"]: s for s in data["sectors"]}
    assert sectors["Semiconductor"]["stock_count"] == 4
    # top 2 by abs change: B (5.0), C (-3.0)
    top_syms = [stk["symbol"] for stk in sectors["Semiconductor"]["stocks"]]
    assert top_syms == ["B", "C"]


async def test_heatmap_market_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """market_filter=TW_TWSE excludes other-market stocks even if they have
    industry_id + change_percent."""
    semi = await _mk_industry(db_session, "Semiconductor")
    s_tw = await _mk_stock(db_session, "2330", "TSMC", semi.id, market=Market.TW_TWSE)
    s_us = await _mk_stock(db_session, "AAPL", "Apple", semi.id, market=Market.US_NASDAQ)

    d = date(2026, 5, 1)
    await _mk_price(db_session, s_tw.id, d, close=895.0, change_pct=4.0)
    await _mk_price(db_session, s_us.id, d, close=200.0, change_pct=1.5)

    resp = await client.get("/api/v1/heatmap/sectors?market_filter=TW_TWSE")
    assert resp.status_code == 200
    data = resp.json()
    sectors = {s["industry"]: s for s in data["sectors"]}
    # Only TSMC counted under Semiconductor
    semi_stocks = sectors["Semiconductor"]["stocks"]
    assert len(semi_stocks) == 1
    assert semi_stocks[0]["symbol"] == "2330"


async def test_heatmap_skips_stocks_without_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The query has `.where(Stock.industry_id.isnot(None))` — stocks
    with NULL industry_id are excluded entirely."""
    s_no_industry = await _mk_stock(db_session, "ORPHAN", "No industry", industry_id=None)
    semi = await _mk_industry(db_session, "Semiconductor")
    s_semi = await _mk_stock(db_session, "2330", "TSMC", semi.id)

    d = date(2026, 5, 1)
    await _mk_price(db_session, s_no_industry.id, d, close=10.0, change_pct=1.0)
    await _mk_price(db_session, s_semi.id, d, close=895.0, change_pct=4.0)

    resp = await client.get("/api/v1/heatmap/sectors")
    assert resp.status_code == 200
    data = resp.json()
    # Semiconductor present with just TSMC; no "Other" sector for the orphan
    sectors = {s["industry"]: s for s in data["sectors"]}
    assert "Semiconductor" in sectors
    assert sectors["Semiconductor"]["stock_count"] == 1
