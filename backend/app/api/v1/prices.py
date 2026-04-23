from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.modules.price_updater.twse import TWSEProvider
from app.modules.price_updater.tpex import TPEXProvider
from app.modules.price_updater.updater import PriceUpdater
from app.schemas.price import (
    BackfillRequest,
    BackfillResponse,
    PriceUpdateResponse,
    StockPriceListResponse,
    StockPriceResponse,
)

router = APIRouter(prefix="/prices", tags=["prices"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/update", response_model=PriceUpdateResponse)
async def trigger_price_update(
    db: DbSession,
) -> PriceUpdateResponse:
    """Trigger a full market price update (TWSE + TPEX)."""
    async with httpx.AsyncClient(timeout=120.0, verify=False) as client:  # noqa: S501 - TWSE SSL cert issue
        providers = [TWSEProvider(client=client), TPEXProvider(client=client)]
        updater = PriceUpdater(providers=providers, session=db, retry_delay=1.0)
        result = await updater.update_all()

    return PriceUpdateResponse(
        total_fetched=result.total_fetched,
        duplicates_skipped=result.duplicates_skipped,
        invalid_skipped=result.invalid_skipped,
        saved=result.saved,
        errors=result.errors,
    )


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_prices(
    req: BackfillRequest,
    db: DbSession,
) -> BackfillResponse:
    """Backfill historical prices using yfinance."""
    import asyncio

    from app.modules.price_updater.yfinance_provider import YFinanceProvider

    provider = YFinanceProvider()
    errors: list[str] = []
    total_saved = 0

    for symbol in req.symbols:
        try:
            prices = await provider.fetch_history(symbol, req.period)
            if prices:
                updater = PriceUpdater(providers=[], session=db)
                await updater._persist_prices(prices)
                await updater._persist_stocks(prices)
                total_saved += len(prices)
        except Exception as e:
            errors.append(f"{symbol}: {str(e)}")
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    return BackfillResponse(
        total_symbols=len(req.symbols),
        total_prices_saved=total_saved,
        errors=errors,
    )


@router.post("/backfill/tw-popular", response_model=BackfillResponse)
async def backfill_tw_popular(
    db: DbSession,
    period: str = Query(default="1y"),
) -> BackfillResponse:
    """Backfill historical prices for stocks in DB via yfinance."""
    import asyncio

    from sqlalchemy import select as sa_select

    from app.models.stock import Stock
    from app.modules.price_updater.yfinance_provider import YFinanceProvider

    result = await db.execute(sa_select(Stock.symbol).limit(100))
    symbols = [row[0] for row in result.all()]

    provider = YFinanceProvider()
    errors: list[str] = []
    total_saved = 0

    for symbol in symbols:
        try:
            prices = await provider.fetch_history(symbol, period)
            if prices:
                updater = PriceUpdater(providers=[], session=db)
                await updater._persist_prices(prices)
                total_saved += len(prices)
            await asyncio.sleep(0.5)
        except Exception as e:
            errors.append(f"{symbol}: {str(e)}")

    return BackfillResponse(
        total_symbols=len(symbols),
        total_prices_saved=total_saved,
        errors=errors,
    )


@router.get("/{symbol}", response_model=StockPriceListResponse)
async def get_stock_prices(
    symbol: str,
    db: DbSession,
    limit: int = Query(default=30, le=365),
    offset: int = Query(default=0, ge=0),
) -> StockPriceListResponse:
    query = (
        select(StockPrice)
        .where(StockPrice.symbol == symbol)
        .order_by(StockPrice.date.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    prices = list(result.scalars().all())

    count_query = select(func.count()).select_from(StockPrice).where(StockPrice.symbol == symbol)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return StockPriceListResponse(
        data=[StockPriceResponse.model_validate(p) for p in prices],
        total=total,
    )
