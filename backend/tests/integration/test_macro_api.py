"""Integration tests for /api/v1/macro/* — Buffett indicator + temperature."""

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
    volume: int = 1_000_000,
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


# ── Buffett indicator ──────────────────────────────────────────────────────


async def test_buffett_indicator_empty_db_returns_fallback(client: AsyncClient) -> None:
    """No stock data → hardcoded fallback ratio + extreme label."""
    resp = await client.get("/api/v1/macro/buffett-indicator")
    assert resp.status_code == 200
    data = resp.json()

    # The schema contract — every field shipped to the UI.
    assert {
        "ratio",
        "label",
        "historical_extreme",
        "source_date",
        "gdp_source",
        "market_cap_source",
    } <= set(data.keys())

    ratio_pct = float(data["ratio"])
    assert ratio_pct > 0
    assert data["label"] in {"極度低估", "低估", "合理", "高估", "極度高估"}
    # Fallback ratio (75 / 25.5 兆) ≈ 294% → "極度高估" + extreme=true.
    assert data["label"] == "極度高估"
    assert data["historical_extreme"] is True
    assert "hardcoded" in data["market_cap_source"]


async def test_buffett_indicator_label_classification_thresholds() -> None:
    """Boundary buckets at 50/75/150/200."""
    from app.api.v1.macro import _classify_buffett

    assert _classify_buffett(Decimal("49.99")) == ("極度低估", True)
    assert _classify_buffett(Decimal("50.00")) == ("低估", False)
    assert _classify_buffett(Decimal("74.99")) == ("低估", False)
    assert _classify_buffett(Decimal("75.00")) == ("合理", False)
    assert _classify_buffett(Decimal("149.99")) == ("合理", False)
    assert _classify_buffett(Decimal("150.00")) == ("高估", False)
    assert _classify_buffett(Decimal("199.99")) == ("高估", False)
    assert _classify_buffett(Decimal("200.00")) == ("極度高估", True)
    assert _classify_buffett(Decimal("400.00")) == ("極度高估", True)


# ── Market temperature ─────────────────────────────────────────────────────


async def test_market_temperature_empty_db_returns_normal(client: AsyncClient) -> None:
    """No basket data → average 0 → 正常."""
    resp = await client.get("/api/v1/macro/market-temperature")
    assert resp.status_code == 200
    data = resp.json()

    assert {
        "score",
        "label",
        "average_change_percent",
        "source_date",
        "index_count",
    } <= set(data.keys())
    assert data["label"] == "正常"
    assert float(data["average_change_percent"]) == 0.0
    assert data["index_count"] == 0
    # avg=0 maps to mid-scale (50).
    assert 49 <= float(data["score"]) <= 51


async def test_market_temperature_hot_when_indices_average_positive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Index basket all up >1% → 熱 label, score >66."""
    d = date(2026, 5, 1)
    for sym in ("^TWII", "^TPEX", "^IXIC"):
        await _mk_stock_with_price(
            db_session, sym, sym, Market.TW_TWSE, d, close=100.0, change_pct=2.5
        )

    resp = await client.get("/api/v1/macro/market-temperature")
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "熱"
    assert float(data["score"]) > 66
    assert data["index_count"] == 3


async def test_market_temperature_cold_when_indices_average_negative(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Index basket all down <-1% → 冷 label, score <34."""
    d = date(2026, 5, 1)
    for sym in ("^TWII", "^TPEX", "^IXIC"):
        await _mk_stock_with_price(
            db_session, sym, sym, Market.TW_TWSE, d, close=100.0, change_pct=-2.0
        )

    resp = await client.get("/api/v1/macro/market-temperature")
    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "冷"
    assert float(data["score"]) < 34


async def test_temperature_score_linear_mapping_clamps() -> None:
    """avg≤-3% → 0, avg≥+3% → 100, mid clamped linearly."""
    from app.api.v1.macro import _temperature_score

    assert _temperature_score(Decimal("-3")) == Decimal("0")
    assert _temperature_score(Decimal("-5")) == Decimal("0")
    assert _temperature_score(Decimal("3")) == Decimal("100")
    assert _temperature_score(Decimal("0")) == Decimal("50")
    # +1.5 → (1.5 + 3) / 6 * 100 = 75
    assert _temperature_score(Decimal("1.5")) == Decimal("75")
