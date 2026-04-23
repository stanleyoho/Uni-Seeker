from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.margin.twse_margin import TWSEMarginProvider
from app.schemas.margin import MarginDataResponse, MarginListResponse, MarginUpdateResponse

router = APIRouter(prefix="/margin", tags=["margin"])


@router.post("/update", response_model=MarginUpdateResponse)
async def update_margin_data(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MarginUpdateResponse:
    """Fetch latest margin trading data from TWSE."""
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        provider = TWSEMarginProvider(client=client)
        data = await provider.fetch_margin_data()

    # TODO: persist to DB (similar to price updater pattern)
    return MarginUpdateResponse(fetched=len(data), saved=len(data))


@router.get("/", response_model=MarginListResponse)
async def get_margin_data(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MarginListResponse:
    """Get latest margin trading data."""
    async with httpx.AsyncClient(timeout=60, verify=False) as client:
        provider = TWSEMarginProvider(client=client)
        data = await provider.fetch_margin_data()

    results = []
    for d in data:
        margin_usage = (d.margin_balance / d.margin_limit * 100) if d.margin_limit > 0 else 0
        short_usage = (d.short_balance / d.short_limit * 100) if d.short_limit > 0 else 0
        ms_ratio = (d.short_balance / d.margin_balance * 100) if d.margin_balance > 0 else 0

        results.append(MarginDataResponse(
            symbol=d.symbol, name=d.name,
            margin_buy=d.margin_buy, margin_sell=d.margin_sell,
            margin_balance=d.margin_balance, margin_limit=d.margin_limit,
            margin_usage_pct=round(margin_usage, 2),
            short_buy=d.short_buy, short_sell=d.short_sell,
            short_balance=d.short_balance, short_limit=d.short_limit,
            short_usage_pct=round(short_usage, 2),
            offset=d.offset,
            margin_short_ratio=round(ms_ratio, 2),
        ))

    return MarginListResponse(data=results, total=len(results))
