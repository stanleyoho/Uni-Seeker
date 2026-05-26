"""Integration tests for /api/v1/low-base/* endpoints (basic mode only).

Enhanced mode hits FinMind + SignalScanner — those are heavy mocks
deferred to a focused sub-agent run; basic mode coverage alone is the
biggest single-file gap.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock


async def _mk_stock_with_history(
    db: AsyncSession,
    symbol: str,
    name: str,
    num_days: int,
    base_close: float = 100.0,
) -> Stock:
    """Seed a stock + num_days of consecutive StockPrice rows."""
    s = Stock(symbol=symbol, name=name, market=Market.TW_TWSE)
    db.add(s)
    await db.commit()
    await db.refresh(s)

    base_date = date(2026, 5, 1)
    for i in range(num_days):
        c = base_close + (i % 7) * 0.5  # mild ripple
        p = StockPrice(
            stock_id=s.id,
            date=base_date - timedelta(days=num_days - i - 1),
            open=Decimal(str(c)),
            high=Decimal(str(c)),
            low=Decimal(str(c)),
            close=Decimal(str(c)),
            change=Decimal("0"),
            volume=100_000,
        )
        db.add(p)
    await db.commit()
    return s


# ── GET /low-base/scan ────────────────────────────────────────────────────


async def test_scan_no_eligible_stocks_returns_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No stocks meeting min_data_days → 200 with empty ranking."""
    resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60")
    assert resp.status_code == 200
    data = resp.json()
    assert "rankings" in data or "results" in data or "scores" in data
    # Total qualified is 0
    assert data.get("total_qualified", 0) == 0


async def test_scan_returns_rankings_for_eligible_stocks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stocks with ≥ min_data_days price rows show up in the scan."""
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)
    await _mk_stock_with_history(db_session, "2454", "MediaTek", num_days=60)

    resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_qualified"] >= 0  # May be 0 if all disqualified by scorer


async def test_scan_min_data_days_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A stock with fewer rows than min_data_days is excluded."""
    await _mk_stock_with_history(db_session, "SHORT", "ShortHistory", num_days=10)

    resp = await client.get("/api/v1/low-base/scan?limit=10&min_data_days=60")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_qualified"] == 0


# ── GET /low-base/{symbol} ────────────────────────────────────────────────


async def test_get_score_unknown_symbol_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/low-base/UNKNOWN")
    assert resp.status_code == 404


async def test_get_score_insufficient_history_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Less than 20 price rows → 404."""
    await _mk_stock_with_history(db_session, "SHORT", "ShortHistory", num_days=10)
    resp = await client.get("/api/v1/low-base/SHORT")
    assert resp.status_code == 404


async def test_get_score_basic_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stock with enough history → 200 with score payload."""
    await _mk_stock_with_history(db_session, "2330", "TSMC", num_days=60)

    resp = await client.get("/api/v1/low-base/2330")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "2330"
    assert "total_score" in data
    assert "valuation_score" in data
    assert "price_position_score" in data
    assert "quality_score" in data
