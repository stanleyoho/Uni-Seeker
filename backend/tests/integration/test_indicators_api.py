from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.main import create_app
from app.models.base import Base
from app.models.enums import Market
from app.models.price import StockPrice

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def app_with_prices():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        for i in range(20):
            price = StockPrice(
                symbol="2330.TW",
                market=Market.TW_TWSE,
                date=date(2026, 4, i + 1),
                open=Decimal(str(885 + i)),
                high=Decimal(str(892 + i)),
                low=Decimal(str(880 + i)),
                close=Decimal(str(890 + i)),
                volume=25_000_000 + i * 100_000,
            )
            session.add(price)
        await session.commit()

    yield app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_indicators(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/indicators/")
        assert resp.status_code == 200
        indicators = resp.json()["indicators"]
        assert "RSI" in indicators
        assert "MACD" in indicators
        assert "KD" in indicators


async def test_calculate_rsi(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "2330.TW", "indicator": "RSI", "params": {"period": 14}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "2330.TW"
        assert data["indicator"] == "RSI"
        assert "RSI" in data["values"]
        assert len(data["values"]["RSI"]) == 20


async def test_calculate_unknown_indicator(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "2330.TW", "indicator": "UNKNOWN"},
        )
        assert resp.status_code == 404


async def test_calculate_no_data(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/indicators/calculate",
            json={"symbol": "INVALID", "indicator": "RSI"},
        )
        assert resp.status_code == 404
