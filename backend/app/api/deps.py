from collections.abc import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.stock import Stock
from app.modules.indicators import create_default_registry
from app.modules.indicators.registry import IndicatorRegistry


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_indicator_registry() -> IndicatorRegistry:
    return create_default_registry()


async def get_stock_or_404(db: AsyncSession, symbol: str) -> Stock:
    """Look up a Stock by its symbol string, raising 404 if not found."""
    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return stock
