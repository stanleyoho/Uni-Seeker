"""Integration tests for the 四大買賣點 scan service + API.

Covers:
  - ``run_best_four_point_scan`` persists per-symbol snapshots into
    ``signal_scans`` and is idempotent for a scan_date.
  - TW-only universe filter (US listings are ignored).
  - ``GET /scanner/best-four-point`` reads the cached snapshot and splits
    rows onto buy / sell boards.
  - Empty-cache path returns ``scan_date=None``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock
from app.services.best_four_point import run_best_four_point_scan

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

# A close series verified to fire the BUY gate + buy_3, with opens/volumes
# overlaid so buy_1 (vol up + close > open today) also fires.
_BUY_CLOSES = [50.0, 46.4, 49.4, 50.0, 47.6, 47.6, 47.5, 46.4, 45.2, 45.5, 46.5]
_SELL_CLOSES = [round(100 - x, 1) for x in _BUY_CLOSES]

_SCAN_DATE = date(2026, 6, 5)


async def _mk_stock(
    db: AsyncSession,
    symbol: str,
    name: str,
    closes: list[float],
    *,
    market: Market = Market.TW_TWSE,
    is_active: bool = True,
    buy_shape: bool = True,
) -> Stock:
    """Seed a stock + daily OHLCV. ``buy_shape`` overlays open/volume so the
    final bar fires point 1 on the relevant side."""
    s = Stock(symbol=symbol, name=name, market=market)
    s.is_active = is_active
    db.add(s)
    await db.commit()
    await db.refresh(s)

    base_date = date(2026, 5, 1)
    n = len(closes)
    for i, c in enumerate(closes):
        is_last = i == n - 1
        # On the last bar: buy_shape → close > open; else → close < open.
        if not is_last:
            open_p = c
        elif buy_shape:
            open_p = c - 5
        else:
            open_p = c + 5
        vol = 5000 if is_last else 1000  # volume spike on last bar
        p = StockPrice(
            stock_id=s.id,
            date=base_date - timedelta(days=n - i - 1),
            open=Decimal(str(open_p)),
            high=Decimal(str(c + 1)),
            low=Decimal(str(c - 1)),
            close=Decimal(str(c)),
            change=Decimal("0"),
            volume=vol,
        )
        db.add(p)
    await db.commit()
    return s


# ── Service ────────────────────────────────────────────────────────────────


async def test_scan_persists_and_classifies(
    db_session: AsyncSession,
) -> None:
    await _mk_stock(db_session, "2330", "TSMC", _BUY_CLOSES, buy_shape=True)
    await _mk_stock(db_session, "2454", "MediaTek", _SELL_CLOSES, buy_shape=False)

    summary = await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)

    assert summary["total_scanned"] == 2
    assert summary["buy_signals"] == 1
    assert summary["sell_signals"] == 1


async def test_scan_ignores_us_listings(
    db_session: AsyncSession,
) -> None:
    await _mk_stock(db_session, "2330", "TSMC", _BUY_CLOSES, buy_shape=True)
    await _mk_stock(
        db_session,
        "AAPL",
        "Apple",
        _BUY_CLOSES,
        market=Market.US_NASDAQ,
        buy_shape=True,
    )

    summary = await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)
    # Only the TW listing is scanned; AAPL (US) is excluded.
    assert summary["total_scanned"] == 1


async def test_scan_ignores_inactive(
    db_session: AsyncSession,
) -> None:
    await _mk_stock(db_session, "9999", "Dead", _BUY_CLOSES, is_active=False, buy_shape=True)
    summary = await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)
    assert summary["total_scanned"] == 0


async def test_scan_is_idempotent_for_day(
    db_session: AsyncSession,
) -> None:
    await _mk_stock(db_session, "2330", "TSMC", _BUY_CLOSES, buy_shape=True)
    s1 = await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)
    s2 = await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)
    # Re-running the same day must not duplicate rows.
    assert s1["total_scanned"] == s2["total_scanned"] == 1


# ── API ──────────────────────────────────────────────────────────────────


async def test_endpoint_returns_cached_boards(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _mk_stock(db_session, "2330", "TSMC", _BUY_CLOSES, buy_shape=True)
    await _mk_stock(db_session, "2454", "MediaTek", _SELL_CLOSES, buy_shape=False)
    await run_best_four_point_scan(db_session, scan_date=_SCAN_DATE)

    resp = await client.get("/api/v1/scanner/best-four-point")
    assert resp.status_code == 200
    body = resp.json()

    assert body["scan_date"] == _SCAN_DATE.isoformat()
    assert body["total_scanned"] == 2
    buy_syms = {r["symbol"] for r in body["buy_signals"]}
    sell_syms = {r["symbol"] for r in body["sell_signals"]}
    assert "2330" in buy_syms
    assert "2454" in sell_syms

    buy_row = next(r for r in body["buy_signals"] if r["symbol"] == "2330")
    assert buy_row["verdict"] == "買進"
    assert buy_row["buy_points"]  # at least one reason
    assert buy_row["last_close"] is not None


async def test_endpoint_empty_cache_returns_null_date(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/scanner/best-four-point")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scan_date"] is None
    assert body["buy_signals"] == []
    assert body["sell_signals"] == []
    assert body["total_scanned"] == 0


async def test_endpoint_not_swallowed_by_symbol_route(
    client: AsyncClient,
) -> None:
    # Ensure `best-four-point` resolves to the dedicated endpoint, not the
    # `/{symbol}` catch-all (which would 404 for a non-existent stock).
    resp = await client.get("/api/v1/scanner/best-four-point")
    assert resp.status_code == 200
    assert "buy_signals" in resp.json()
