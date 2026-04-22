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
async def app_with_db():
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
        price = StockPrice(
            symbol="2330.TW",
            market=Market.TW_TWSE,
            date=date(2026, 4, 22),
            open=Decimal("885.00"),
            high=Decimal("892.00"),
            low=Decimal("880.00"),
            close=Decimal("890.00"),
            volume=25_000_000,
        )
        session.add(price)
        await session.commit()

    yield app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_get_prices(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/prices/2330.TW")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["data"][0]["symbol"] == "2330.TW"
        assert data["data"][0]["close"] == "890.0000"


async def test_get_prices_empty(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/prices/INVALID")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


async def test_health(app_with_db) -> None:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
