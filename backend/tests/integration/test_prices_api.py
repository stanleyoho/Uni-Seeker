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
