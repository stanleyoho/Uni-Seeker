from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

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
async def app_with_screener_data():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed: rising stock and falling stock
    async with session_factory() as session:
        stock_rise = Stock(symbol="RISE.TW", name="Rise Stock", market=Market.TW_TWSE)
        stock_fall = Stock(symbol="FALL.TW", name="Fall Stock", market=Market.TW_TWSE)
        session.add_all([stock_rise, stock_fall])
        await session.flush()

        # Anchor on today so seed data always falls within the screener's
        # 30-day recent-data cutoff (otherwise rows get filtered out).
        today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
        start = today - timedelta(days=19)
        for i in range(20):
            d = start + timedelta(days=i)
            session.add(
                StockPrice(
                    stock_id=stock_rise.id,
                    date=d,
                    open=Decimal(str(100 + i)),
                    high=Decimal(str(102 + i)),
                    low=Decimal(str(98 + i)),
                    close=Decimal(str(101 + i)),
                    volume=10_000_000,
                )
            )
            session.add(
                StockPrice(
                    stock_id=stock_fall.id,
                    date=d,
                    open=Decimal(str(100 - i)),
                    high=Decimal(str(102 - i)),
                    low=Decimal(str(98 - i)),
                    close=Decimal(str(99 - i)),
                    volume=10_000_000,
                )
            )
        await session.commit()

    yield app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_screen_finds_oversold(app_with_screener_data) -> None:
    transport = ASGITransport(app=app_with_screener_data)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/screener/screen",
            json={
                "conditions": [
                    {"indicator": "RSI", "params": {"period": 14}, "op": "<", "value": 30}
                ],
                "operator": "AND",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        symbols = [r["symbol"] for r in data["results"]]
        assert "FALL.TW" in symbols
        assert "RISE.TW" not in symbols


async def test_screen_empty_result(app_with_screener_data) -> None:
    transport = ASGITransport(app=app_with_screener_data)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/screener/screen",
            json={
                "conditions": [
                    {"indicator": "RSI", "params": {"period": 14}, "op": "<", "value": 0}
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
