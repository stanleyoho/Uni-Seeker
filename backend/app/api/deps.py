from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.modules.indicators import create_default_registry
from app.modules.indicators.registry import IndicatorRegistry


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_indicator_registry() -> IndicatorRegistry:
    return create_default_registry()
