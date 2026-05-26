from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.auth import create_access_token
from app.main import create_app
from app.models.base import Base
from app.models.enums import Market, UserTier
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.user import User

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

    # Seed a PRO user so require_auth + require_tier(PRO) pass.
    # Task 6 added these guards to backtest endpoints.
    async with session_factory() as session:
        user = User(
            email="pro_test@example.com",
            hashed_password="x" * 60,
            username="pro_test",
        )
        user.tier = UserTier.PRO
        session.add(user)
        await session.flush()
        token = create_access_token(user.id, user.email)
        headers = {"Authorization": f"Bearer {token}"}

        stock = Stock(symbol="TEST.TW", name="Test Stock", market=Market.TW_TWSE)
        session.add(stock)
        await session.flush()

        for i in range(60):
            d = date(2026, 1, 1) + timedelta(days=i)
            c = 100.0 - i * 0.5 if i < 30 else 85.0 + (i - 30) * 1.0
            session.add(
                StockPrice(
                    stock_id=stock.id,
                    date=d,
                    open=Decimal(str(c - 1)),
                    high=Decimal(str(c + 2)),
                    low=Decimal(str(c - 2)),
                    close=Decimal(str(c)),
                    volume=10_000_000,
                )
            )
        await session.commit()
    yield app, headers
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_strategies(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /strategies/ is currently unauthenticated; sending the header is harmless.
        resp = await client.get("/api/v1/strategies/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        names = [s["name"] for s in data["strategies"]]
        assert "ma_crossover" in names
        assert "rsi_oversold" in names


async def test_run_backtest(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TEST.TW",
                "strategy": "rsi_oversold",
                "initial_capital": 1000000,
                "position_size": 0.3,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TEST.TW"
        assert data["strategy"] == "rsi_oversold"
        assert "metrics" in data
        assert len(data["equity_curve"]) == 60


async def test_unknown_strategy(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TEST.TW",
                "strategy": "nonexistent",
            },
            headers=headers,
        )
        assert resp.status_code == 400


async def test_insufficient_data(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "NODATA.TW",
                "strategy": "rsi_oversold",
            },
            headers=headers,
        )
        # If stock not found, returns 404
        assert resp.status_code == 404


# ── /run/composite ────────────────────────────────────────────────────────


async def test_composite_too_few_strategies_400(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run/composite",
            json={
                "symbol": "TEST.TW",
                "strategies": ["ma_crossover"],
                "mode": "majority",
            },
            headers=headers,
        )
        assert resp.status_code == 400
        assert "at least 2" in resp.json()["message"]


async def test_composite_invalid_mode_400(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run/composite",
            json={
                "symbol": "TEST.TW",
                "strategies": ["ma_crossover", "rsi_oversold"],
                "mode": "weird",
            },
            headers=headers,
        )
        assert resp.status_code == 400
        assert "Invalid mode" in resp.json()["message"]


async def test_composite_unknown_strategy_400(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run/composite",
            json={
                "symbol": "TEST.TW",
                "strategies": ["ma_crossover", "no_such_strategy"],
                "mode": "majority",
            },
            headers=headers,
        )
        assert resp.status_code == 400


async def test_composite_happy_path(app_with_prices) -> None:
    app, headers = app_with_prices
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/backtest/run/composite",
            json={
                "symbol": "TEST.TW",
                "strategies": ["ma_crossover", "rsi_oversold"],
                "mode": "majority",
                "strategy_params": {"ma_crossover": {"short_period": 5, "long_period": 20}},
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert "composite" in data["strategy"]
        assert "metrics" in data
        assert "equity_curve" in data
