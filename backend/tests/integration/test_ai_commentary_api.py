"""Integration tests for GET /api/v1/stocks/{symbol}/ai-commentary.

Asserts:
  - 404 when the stock doesn't exist
  - 404 when no price data exists for the symbol
  - 200 with composed narrative when price + indicators are available
  - Sector hot-top-3 branch fires when the stock's industry is in the
    top 3 by avg change_percent on the target date
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.enums import Market
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_series(
    db_session: AsyncSession, stock: Stock, days: int, start_close: float
) -> None:
    """Seed `days` daily prices ending today, with a mild uptrend so MA/RSI
    actually have data to work with."""
    base_date = date(2026, 6, 2)
    for i in range(days):
        d = base_date - timedelta(days=days - 1 - i)
        # Mild +0.5% daily drift so RSI lands in the bullish band.
        close = start_close * (1.005 ** i)
        prev_close = start_close * (1.005 ** (i - 1)) if i > 0 else close
        change = close - prev_close
        chg_pct = (change / prev_close * 100) if prev_close else 0.0
        db_session.add(
            StockPrice(
                stock_id=stock.id,
                date=d,
                open=Decimal(str(round(close * 0.998, 4))),
                high=Decimal(str(round(close * 1.01, 4))),
                low=Decimal(str(round(close * 0.99, 4))),
                close=Decimal(str(round(close, 4))),
                volume=20_000_000 + i * 100_000,
                change=Decimal(str(round(change, 4))),
                change_percent=Decimal(str(round(chg_pct, 4))),
            )
        )
    await db_session.commit()


async def test_ai_commentary_404_for_unknown_symbol(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/stocks/UNKNOWN/ai-commentary")
    assert resp.status_code == 404


async def test_ai_commentary_404_when_no_prices(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    s = Stock(symbol="9999.TW", name="NoPrices", market=Market.TW_TWSE)
    db_session.add(s)
    await db_session.commit()

    resp = await client.get("/api/v1/stocks/9999.TW/ai-commentary")
    assert resp.status_code == 404
    # Global error handler shapes the body as { error, message, ... }; the
    # original FastAPI `detail` lands in `message`.
    body = resp.json()
    assert "No price data" in body.get("message", "") or "No price data" in body.get(
        "detail", ""
    )


async def test_ai_commentary_full_response(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ind = Industry(name="半導體業")
    db_session.add(ind)
    await db_session.commit()
    await db_session.refresh(ind)

    s = Stock(symbol="2330.TW", name="台積電", market=Market.TW_TWSE)
    s.industry_id = ind.id
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    await _seed_series(db_session, s, days=40, start_close=800.0)

    resp = await client.get("/api/v1/stocks/2330.TW/ai-commentary")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["symbol"] == "2330.TW"
    assert body["date"] == "2026-06-02"
    assert isinstance(body["commentary"], str)
    assert len(body["commentary"]) >= 50
    assert "2330.TW" in body["commentary"]
    # Bullish drift → some up/strong language
    assert any(token in body["commentary"] for token in ["上漲", "偏多", "偏強", "站上"])
    # Confidence in (0, 1]
    assert 0.0 < body["confidence"] <= 1.0
    # Sources include at least price + ma20
    kinds = {s["kind"] for s in body["sources"]}
    assert "price" in kinds
    assert "ma20" in kinds


async def test_ai_commentary_sector_hot_branch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """When the stock's industry is in the top 3 by avg change_percent on
    the target date, the narrative MUST mention 熱門族群."""
    target = date(2026, 6, 2)

    semi = Industry(name="半導體業")
    other = Industry(name="紡織業")
    db_session.add_all([semi, other])
    await db_session.commit()
    await db_session.refresh(semi)
    await db_session.refresh(other)

    # Main stock in 半導體業 — give it a high change_percent.
    tsmc = Stock(symbol="2330.TW", name="台積電", market=Market.TW_TWSE)
    tsmc.industry_id = semi.id
    db_session.add(tsmc)
    # Drag stock in 紡織業 — negative change_percent, so semi clearly leads.
    drag = Stock(symbol="1402.TW", name="遠東新", market=Market.TW_TWSE)
    drag.industry_id = other.id
    db_session.add(drag)
    await db_session.commit()
    await db_session.refresh(tsmc)
    await db_session.refresh(drag)

    # 40 days of history for 2330 so indicators have inputs.
    await _seed_series(db_session, tsmc, days=40, start_close=800.0)
    # Make sure today's row for 2330 has a big positive change_percent.
    # The series builder already gave us +0.5% daily; we re-stamp today.
    today_row_q = await db_session.execute(
        # use raw SQL-equivalent via ORM
        StockPrice.__table__.select()
        .where(StockPrice.stock_id == tsmc.id)
        .where(StockPrice.date == target)
    )
    # Add a strong dragger today for 紡織業 with negative change_percent.
    db_session.add(
        StockPrice(
            stock_id=drag.id,
            date=target,
            open=Decimal("30.0"),
            high=Decimal("30.0"),
            low=Decimal("28.0"),
            close=Decimal("28.5"),
            volume=1_000_000,
            change=Decimal("-1.5"),
            change_percent=Decimal("-5.0"),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/v1/stocks/2330.TW/ai-commentary")
    assert resp.status_code == 200
    body = resp.json()
    # Semi should rank #1 today (positive ~0.5% vs negative -5.0%).
    assert "半導體業" in body["commentary"]
    assert "熱門族群" in body["commentary"]
    assert any(s["kind"] == "sector" for s in body["sources"])
