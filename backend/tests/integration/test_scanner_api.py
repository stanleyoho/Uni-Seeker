"""Integration tests for /api/v1/scanner/* endpoints.

Covers `POST /scan` (multi-stock) and `GET /{symbol}` (single stock).
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


async def _mk_stock_with_prices(
    db: AsyncSession,
    symbol: str,
    name: str,
    closes: list[float],
    market: Market = Market.TW_TWSE,
    is_active: bool = True,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=market)
    s.is_active = is_active
    db.add(s)
    await db.commit()
    await db.refresh(s)

    base_date = date(2026, 5, 1)
    for i, c in enumerate(closes):
        p = StockPrice(
            stock_id=s.id,
            date=base_date - timedelta(days=len(closes) - i - 1),
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


# ── POST /scan ────────────────────────────────────────────────────────────


async def test_scan_no_stocks_returns_404(client: AsyncClient) -> None:
    """Empty DB → 404."""
    resp = await client.post("/api/v1/scanner/scan", json={"limit": 10})
    assert resp.status_code == 404


async def test_scan_with_symbols_returns_results(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Seed two stocks with sufficient price history; scan returns signals."""
    closes = [100.0 + i * 0.5 for i in range(60)]  # 60 days
    await _mk_stock_with_prices(db_session, "2330", "TSMC", closes)
    await _mk_stock_with_prices(db_session, "2454", "MediaTek", closes)

    resp = await client.post(
        "/api/v1/scanner/scan", json={"symbols": ["2330", "2454"], "limit": 10}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scanned"] == 2
    assert "scan_date" in data
    assert len(data["results"]) <= 10


async def test_scan_invalid_strategy_key_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    closes = [100.0 + i * 0.5 for i in range(60)]
    await _mk_stock_with_prices(db_session, "2330", "TSMC", closes)

    resp = await client.post(
        "/api/v1/scanner/scan",
        json={"symbols": ["2330"], "strategy_keys": ["nonexistent_strategy"], "limit": 5},
    )
    assert resp.status_code == 400
    assert "Unknown strategy keys" in resp.json()["message"]


async def test_scan_filters_inactive_stocks(client: AsyncClient, db_session: AsyncSession) -> None:
    """is_active=False stocks are excluded from the scan query."""
    closes = [100.0] * 60
    await _mk_stock_with_prices(db_session, "ACTIVE", "Active", closes, is_active=True)
    await _mk_stock_with_prices(db_session, "INACTIVE", "Inactive", closes, is_active=False)

    resp = await client.post(
        "/api/v1/scanner/scan", json={"symbols": ["ACTIVE", "INACTIVE"], "limit": 10}
    )
    assert resp.status_code == 200
    data = resp.json()
    # Only ACTIVE counted
    assert data["total_scanned"] == 1


# ── GET /{symbol} ─────────────────────────────────────────────────────────


async def test_get_signals_unknown_symbol_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/scanner/UNKNOWN")
    assert resp.status_code == 404


async def test_get_signals_insufficient_data_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Only 1 price point → 400 insufficient."""
    await _mk_stock_with_prices(db_session, "2330", "TSMC", [100.0])

    resp = await client.get("/api/v1/scanner/2330")
    assert resp.status_code == 400


async def test_get_signals_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    closes = [100.0 + i * 0.5 for i in range(60)]
    await _mk_stock_with_prices(db_session, "2330", "TSMC", closes)

    resp = await client.get("/api/v1/scanner/2330")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "2330"
    assert "composite_action" in data
    assert "score" in data


async def test_get_signals_strategy_filter(client: AsyncClient, db_session: AsyncSession) -> None:
    """strategy_keys query param scopes the evaluation to selected strategies."""
    closes = [100.0 + i * 0.5 for i in range(60)]
    await _mk_stock_with_prices(db_session, "2330", "TSMC", closes)

    resp = await client.get(
        "/api/v1/scanner/2330?strategy_keys=ma_crossover&strategy_keys=rsi_oversold"
    )
    assert resp.status_code == 200


async def test_get_signals_unknown_strategy_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    closes = [100.0 + i * 0.5 for i in range(60)]
    await _mk_stock_with_prices(db_session, "2330", "TSMC", closes)

    resp = await client.get("/api/v1/scanner/2330?strategy_keys=fake_strategy")
    assert resp.status_code == 400
