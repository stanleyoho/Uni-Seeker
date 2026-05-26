from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Market
from app.models.price import StockPrice
from app.models.stock import Stock


@pytest.mark.asyncio
async def test_get_prices_success(client: AsyncClient, db_session: AsyncSession):
    # 1. Seed a stock
    stock = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
    db_session.add(stock)
    await db_session.flush()

    # 2. Seed some prices
    prices = [
        StockPrice(
            stock_id=stock.id,
            date=date(2024, 1, 1),
            open=Decimal("500"),
            high=Decimal("510"),
            low=Decimal("495"),
            close=Decimal("505"),
            volume=1000000,
            change=Decimal("5"),
            change_percent=Decimal("1.0"),
        )
    ]
    db_session.add_all(prices)
    await db_session.commit()

    # 3. Test the API
    response = await client.get("/api/v1/prices/2330.TW?limit=10")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) == 1
    assert data["data"][0]["symbol"] == "2330.TW"
    # Verify DecimalStr serialization (should be string)
    assert isinstance(data["data"][0]["close"], str)
    assert float(data["data"][0]["close"]) == 505.0


@pytest.mark.asyncio
async def test_get_prices_not_found(client: AsyncClient):
    response = await client.get("/api/v1/prices/9999.TW")
    assert response.status_code == 404


# ── POST /update / /backfill — extended coverage ─────────────────────────


@pytest.mark.asyncio
async def test_trigger_price_update_mocked(client: AsyncClient, db_session: AsyncSession) -> None:
    from typing import ClassVar
    from unittest.mock import AsyncMock, patch

    class _FakeResult:
        total_fetched = 100
        duplicates_skipped = 10
        invalid_skipped = 2
        saved = 88
        errors: ClassVar[list[str]] = []

    with patch("app.api.v1.prices.PriceUpdater") as updater_cls:
        updater_cls.return_value.update_all = AsyncMock(return_value=_FakeResult())
        resp = await client.post("/api/v1/prices/update")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_fetched"] == 100
    assert data["saved"] == 88


@pytest.mark.asyncio
async def test_backfill_with_mock_provider(client: AsyncClient, db_session: AsyncSession) -> None:
    """Mock yfinance + PriceUpdater._persist_* so no network."""
    from unittest.mock import AsyncMock, patch

    fake_prices = [object()]
    with (
        patch("app.modules.price_updater.yfinance_provider.YFinanceProvider") as prov_cls,
        patch("app.api.v1.prices.PriceUpdater") as updater_cls,
        patch("asyncio.sleep", AsyncMock(return_value=None)),
    ):
        prov_cls.return_value.fetch_history = AsyncMock(return_value=fake_prices)
        updater_cls.return_value._persist_prices = AsyncMock(return_value=None)
        updater_cls.return_value._persist_stocks = AsyncMock(return_value=None)

        resp = await client.post(
            "/api/v1/prices/backfill",
            json={"symbols": ["2330", "0050"], "period": "1y"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_symbols"] == 2
    assert data["total_prices_saved"] == 2
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_backfill_collects_per_symbol_errors(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Per-symbol provider exception lands in errors[]."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.modules.price_updater.yfinance_provider.YFinanceProvider") as prov_cls,
        patch("asyncio.sleep", AsyncMock(return_value=None)),
    ):
        prov_cls.return_value.fetch_history = AsyncMock(side_effect=RuntimeError("provider boom"))

        resp = await client.post(
            "/api/v1/prices/backfill",
            json={"symbols": ["BAD"], "period": "1y"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_prices_saved"] == 0
    assert "BAD" in data["errors"][0]
    assert "boom" in data["errors"][0]


@pytest.mark.asyncio
async def test_backfill_tw_popular_empty_db(client: AsyncClient) -> None:
    """No Stock rows → empty backfill response."""
    from unittest.mock import AsyncMock, patch

    with patch("asyncio.sleep", AsyncMock(return_value=None)):
        resp = await client.post("/api/v1/prices/backfill/tw-popular")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_symbols"] == 0


@pytest.mark.asyncio
async def test_backfill_tw_popular_pulls_db_symbols(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Stock rows in DB drive the symbol loop."""
    from unittest.mock import AsyncMock, patch

    db_session.add(Stock(symbol="2330", name="TSMC", market=Market.TW_TWSE))
    db_session.add(Stock(symbol="0050", name="Yuanta", market=Market.TW_TWSE))
    await db_session.commit()

    with (
        patch("app.modules.price_updater.yfinance_provider.YFinanceProvider") as prov_cls,
        patch("app.api.v1.prices.PriceUpdater") as updater_cls,
        patch("asyncio.sleep", AsyncMock(return_value=None)),
    ):
        prov_cls.return_value.fetch_history = AsyncMock(return_value=[object()])
        updater_cls.return_value._persist_prices = AsyncMock(return_value=None)

        resp = await client.post("/api/v1/prices/backfill/tw-popular?period=6mo")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_symbols"] == 2
    assert data["total_prices_saved"] == 2
