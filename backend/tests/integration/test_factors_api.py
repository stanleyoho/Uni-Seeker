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
from app.models.stock import Stock

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
        stock = Stock(symbol="2330.TW", name="TSMC", market=Market.TW_TWSE)
        session.add(stock)
        # Benchmark used by the BETA factor.
        bench = Stock(symbol="0050.TW", name="Yuanta TW50", market=Market.TW_TWSE)
        session.add(bench)
        await session.flush()

        base = date(2026, 1, 1).toordinal()
        for s in (stock, bench):
            for i in range(70):
                session.add(
                    StockPrice(
                        stock_id=s.id,
                        date=date.fromordinal(base + i),
                        open=Decimal(str(100 + i)),
                        high=Decimal(str(102 + i)),
                        low=Decimal(str(98 + i)),
                        close=Decimal(str(101 + i)),
                        volume=1_000_000 + i * 10_000,
                    )
                )
        await session.commit()

    yield app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_list_factors(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/factors/")
        assert resp.status_code == 200
        names = {f["name"] for f in resp.json()["factors"]}
        assert {"KMID", "ROC5", "RSI14", "BETA60"} <= names
        # Every factor carries a formula string.
        assert all(f["formula"] for f in resp.json()["factors"])


async def test_compute_factor_vector(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/factors/compute", json={"symbol": "2330.TW"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "2330.TW"
        assert data["bar_count"] == 70
        # With 70 bars, all windowed factors are warmed up.
        assert data["factors"]["KMID"] is not None
        assert data["factors"]["ROC5"] is not None
        assert data["factors"]["RSI14"] is not None
        # Beta vs a perfectly correlated benchmark (same price series) ~= 1.
        assert data["factors"]["BETA60"] == pytest.approx(1.0, abs=1e-3)
        assert data["composite_momentum"] is not None


async def test_compute_unknown_symbol_404(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/factors/compute", json={"symbol": "NOPE"})
        assert resp.status_code == 404


async def test_compute_rejects_extra_field(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/factors/compute",
            json={"symbol": "2330.TW", "bogus": 1},
        )
        assert resp.status_code == 422  # StrictModel rejects unknown fields


async def test_batch_compute(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/factors/compute/batch",
            json={"symbols": ["2330.TW", "0050.TW"]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert {r["symbol"] for r in results} == {"2330.TW", "0050.TW"}


async def test_batch_empty_422(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/factors/compute/batch", json={"symbols": []})
        assert resp.status_code == 422


async def test_batch_over_limit_422(app_with_prices) -> None:
    transport = ASGITransport(app=app_with_prices)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/factors/compute/batch",
            json={"symbols": [f"S{i}.TW" for i in range(51)]},
        )
        assert resp.status_code == 422
