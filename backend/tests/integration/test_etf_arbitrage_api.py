"""Integration tests for /api/v1/etf-arbitrage/* endpoints.

FinMind's TaiwanStockNAV dataset is stubbed via FastAPI's
`dependency_overrides` — no real network calls. The stub returns a
fixed NAV per symbol so the premium% math is deterministic.

Coverage targets:
  - Endpoint registered and reachable.
  - Response shape matches `ETFArbitrageListResponse`.
  - Premium / discount math is correct given known inputs.
  - `direction=premium` filters out discount rows.
  - `type=股票型` filters out 槓桿反向 rows.
  - Empty-NAV-data path returns `message` and empty `data`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from app.api.v1.etf_arbitrage import _get_service
from app.main import create_app
from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.etf_arbitrage import ETFArbitrageService

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


# ────────────────────────────────────────────────────────────────────
# Stub provider
# ────────────────────────────────────────────────────────────────────


class _StubFinMindProvider:
    """Minimal stand-in for FinMindMarketProvider.

    Built around a (symbol → nav) map. Returns FinMind-shaped records
    (`[{date, stock_id, nav}, ...]`). Used in place of the real
    provider via dependency-override in tests.
    """

    def __init__(self, nav_map: dict[str, Decimal]) -> None:
        self._nav_map = nav_map

    async def fetch_etf_nav(
        self,
        stock_id: str,
        start_date: str,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        nav = self._nav_map.get(stock_id)
        if nav is None:
            return []
        return [
            {
                "date": date.today().isoformat(),
                "stock_id": stock_id,
                "nav": str(nav),
            }
        ]


def _service_with_stub(nav_map: dict[str, Decimal]) -> ETFArbitrageService:
    return ETFArbitrageService(provider=_StubFinMindProvider(nav_map))  # type: ignore[arg-type]


# ────────────────────────────────────────────────────────────────────
# Seed helpers
# ────────────────────────────────────────────────────────────────────


async def _seed_etf(
    db: AsyncSession,
    *,
    symbol: str,
    name: str,
    market: Market,
    close: Decimal,
    change: Decimal = Decimal("0"),
    change_percent: Decimal = Decimal("0"),
    volume: int = 1_000_000,
) -> Stock:
    s = Stock(symbol=symbol, name=name, market=market)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    p = StockPrice(
        stock_id=s.id,
        date=date.today() - timedelta(days=1),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        change=change,
        change_percent=change_percent,
    )
    db.add(p)
    await db.commit()
    return s


# ────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────


@pytest.fixture
def _override_service():
    """Yield a setter; tests call it with a nav_map to install the stub."""
    app = create_app()

    def _set(nav_map: dict[str, Decimal]) -> None:
        app.dependency_overrides[_get_service] = lambda: _service_with_stub(nav_map)

    return _set, app


async def test_list_premium_math_and_shape(client: AsyncClient, db_session: AsyncSession) -> None:
    """Endpoint returns rows with expected premium% and correct shape."""
    # market = 90.40, nav = 89.14 → premium ~ +1.41%
    await _seed_etf(
        db_session,
        symbol="00830",
        name="國泰費城半導體ETF",
        market=Market.TW_TWSE,
        close=Decimal("90.40"),
        change=Decimal("0.50"),
        change_percent=Decimal("0.56"),
    )

    # Override the service factory on the live app the `client` fixture
    # has already bound, so the override actually takes effect.
    from app.api.v1.etf_arbitrage import _get_service as svc_dep

    client._transport.app.dependency_overrides[svc_dep] = lambda: _service_with_stub(  # type: ignore[attr-defined]
        {"00830": Decimal("89.14")}
    )

    resp = await client.get("/api/v1/etf-arbitrage/list")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" in body
    assert "stats" in body
    assert len(body["data"]) == 1
    row = body["data"][0]
    # Shape
    expected_keys = {
        "symbol",
        "name",
        "type",
        "estimated_nav",
        "market_price",
        "change",
        "change_percent",
        "premium_percent",
        "sentiment_level",
        "volume_lots",
        "trend",
    }
    assert expected_keys.issubset(row.keys())
    assert row["symbol"] == "00830"
    assert row["estimated_nav"] == "89.14"
    assert row["market_price"] == "90.40"
    # (90.40 - 89.14)/89.14 * 100 = 1.4135 → "+1.41"
    assert row["premium_percent"] == "+1.41"
    # 1.41 > 1.0 threshold → 過熱
    assert row["sentiment_level"] == "過熱"

    stats = body["stats"]
    assert stats["total_monitored"] == 1
    assert stats["premium_count"] == 1
    assert stats["discount_count"] == 0
    assert stats["max_premium_etf"]["symbol"] == "00830"


async def test_direction_filter_discount(client: AsyncClient, db_session: AsyncSession) -> None:
    """direction=discount returns only rows with premium% < 0."""
    await _seed_etf(
        db_session,
        symbol="00830",
        name="國泰費城半導體ETF",
        market=Market.TW_TWSE,
        close=Decimal("90.40"),
    )
    await _seed_etf(
        db_session,
        symbol="00736",
        name="國泰新興市場ETF",
        market=Market.TW_TWSE,
        close=Decimal("19.70"),
    )

    from app.api.v1.etf_arbitrage import _get_service as svc_dep

    client._transport.app.dependency_overrides[svc_dep] = lambda: _service_with_stub(  # type: ignore[attr-defined]
        {"00830": Decimal("89.14"), "00736": Decimal("20.00")}
    )

    resp = await client.get("/api/v1/etf-arbitrage/list?direction=discount")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "00736"
    assert body["data"][0]["premium_percent"].startswith("-")


async def test_type_filter_excludes_leveraged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """type=股票型 excludes leveraged ETFs."""
    await _seed_etf(
        db_session,
        symbol="00830",
        name="國泰費城半導體ETF",
        market=Market.TW_TWSE,
        close=Decimal("90.40"),
    )
    await _seed_etf(
        db_session,
        symbol="00633L",
        name="富邦上証正2 ETF",
        market=Market.TW_TWSE,
        close=Decimal("25.10"),
    )

    from app.api.v1.etf_arbitrage import _get_service as svc_dep

    client._transport.app.dependency_overrides[svc_dep] = lambda: _service_with_stub(  # type: ignore[attr-defined]
        {"00830": Decimal("89.14"), "00633L": Decimal("25.00")}
    )

    resp = await client.get("/api/v1/etf-arbitrage/list?type=股票型")
    assert resp.status_code == 200
    body = resp.json()
    symbols = [row["symbol"] for row in body["data"]]
    assert "00830" in symbols
    assert "00633L" not in symbols


async def test_empty_nav_returns_message(client: AsyncClient, db_session: AsyncSession) -> None:
    """When FinMind returns no NAV data, response carries a message
    instead of fabricating zeros."""
    await _seed_etf(
        db_session,
        symbol="00830",
        name="國泰費城半導體ETF",
        market=Market.TW_TWSE,
        close=Decimal("90.40"),
    )

    from app.api.v1.etf_arbitrage import _get_service as svc_dep

    # Empty nav_map → stub returns [] for every fetch.
    client._transport.app.dependency_overrides[svc_dep] = lambda: _service_with_stub(  # type: ignore[attr-defined]
        {}
    )

    resp = await client.get("/api/v1/etf-arbitrage/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["message"]
    assert "FinMind" in body["message"]
