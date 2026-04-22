from collections.abc import AsyncGenerator
from decimal import Decimal
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.enums import Market
from app.models.price import StockPrice

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def sample_prices() -> list[StockPrice]:
    """20 days of TSMC price data for indicator testing."""
    base_prices = [
        (885, 892, 880, 890, 25_000_000),
        (890, 895, 888, 893, 22_000_000),
        (893, 900, 891, 898, 28_000_000),
        (898, 902, 895, 896, 20_000_000),
        (896, 898, 890, 891, 18_000_000),
        (891, 893, 885, 887, 23_000_000),
        (887, 890, 882, 883, 21_000_000),
        (883, 886, 878, 880, 26_000_000),
        (880, 884, 876, 882, 24_000_000),
        (882, 888, 880, 886, 22_000_000),
        (886, 892, 884, 891, 25_000_000),
        (891, 896, 889, 894, 23_000_000),
        (894, 899, 892, 897, 27_000_000),
        (897, 903, 895, 901, 30_000_000),
        (901, 908, 899, 906, 32_000_000),
        (906, 910, 903, 905, 28_000_000),
        (905, 907, 900, 902, 22_000_000),
        (902, 905, 898, 903, 24_000_000),
        (903, 909, 901, 908, 29_000_000),
        (908, 915, 906, 913, 35_000_000),
    ]
    return [
        StockPrice(
            symbol="2330.TW",
            market=Market.TW_TWSE,
            date=date(2026, 4, d + 1),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=v,
        )
        for d, (o, h, l, c, v) in enumerate(base_prices)
    ]
