from datetime import date, timedelta
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

    # Seed 60 days of falling-then-rising prices
    async with session_factory() as session:
        for i in range(60):
            d = date(2026, 1, 1) + timedelta(days=i)
            if i < 30:
                c = 100.0 - i * 0.5
            else:
                c = 85.0 + (i - 30) * 1.0
            session.add(StockPrice(
                symbol="TEST.TW", market=Market.TW_TWSE, date=d,
                open=Decimal(str(c - 1)), high=Decimal(str(c + 2)),
                low=Decimal(str(c - 2)), close=Decimal(str(c)), volume=10_000_000,
            ))
        await session.commit()
    yield app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_strategies(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/strategies/")
        assert resp.status_code == 200
        data = resp.json()
        names = [s["name"] for s in data["strategies"]]
        assert "ma_crossover" in names
        assert "rsi_oversold" in names


async def test_run_backtest(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/backtest/run", json={
            "symbol": "TEST.TW",
            "strategy": "rsi_oversold",
            "initial_capital": 1000000,
            "position_size": 0.3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TEST.TW"
        assert data["strategy"] == "rsi_oversold"
        assert "metrics" in data
        assert len(data["equity_curve"]) == 60


async def test_unknown_strategy(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/backtest/run", json={
            "symbol": "TEST.TW", "strategy": "nonexistent",
        })
        assert resp.status_code == 400


async def test_insufficient_data(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/backtest/run", json={
            "symbol": "NODATA.TW", "strategy": "rsi_oversold",
        })
        assert resp.status_code == 400
