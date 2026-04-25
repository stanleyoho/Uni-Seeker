"""Market overview API: indices, movers (gainers/losers/volume)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.models.stock import Stock

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/market", tags=["market"])


# -- Schemas ------------------------------------------------------------------


class MarketMover(BaseModel):
    symbol: str
    name: str
    market: str
    close: float
    change: float
    change_percent: float
    volume: int


class MarketMoversResponse(BaseModel):
    gainers: list[MarketMover]
    losers: list[MarketMover]
    most_active: list[MarketMover]
    date: str | None


class MarketIndex(BaseModel):
    symbol: str
    name: str
    value: float
    change: float
    change_percent: float


class MarketIndicesResponse(BaseModel):
    indices: list[MarketIndex]


# -- Helpers ------------------------------------------------------------------


def _to_mover(row: tuple) -> MarketMover:
    return MarketMover(
        symbol=row.symbol,
        name=row.name or row.symbol,
        market=row.market,
        close=float(row.close or 0),
        change=float(row.change or 0),
        change_percent=float(row.change_percent or 0),
        volume=int(row.volume or 0),
    )


# -- Endpoints ----------------------------------------------------------------


@router.get("/movers")
async def get_market_movers(
    db: DbSession,
    market_filter: str | None = Query(None, description="TW_TWSE, TW_TPEX, US_NYSE, US_NASDAQ"),
    limit: int = Query(default=10, le=50),
) -> MarketMoversResponse:
    """Top gainers, losers, and most active stocks for the latest trading day."""

    # Find latest date with data
    latest_q = select(func.max(StockPrice.date))
    if market_filter:
        latest_q = latest_q.join(Stock, Stock.id == StockPrice.stock_id).where(
            Stock.market == market_filter
        )
    latest_result = await db.execute(latest_q)
    latest_date = latest_result.scalar()

    if not latest_date:
        return MarketMoversResponse(gainers=[], losers=[], most_active=[], date=None)

    # Base query: join price + stock for name/symbol/market, filter by latest date
    base = (
        select(
            Stock.symbol,
            Stock.name,
            Stock.market,
            StockPrice.close,
            StockPrice.change,
            StockPrice.change_percent,
            StockPrice.volume,
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .where(StockPrice.date == latest_date)
        .where(StockPrice.change_percent.isnot(None))
    )
    if market_filter:
        base = base.where(Stock.market == market_filter)

    # Gainers (desc by change_percent)
    gainers_q = base.order_by(
        desc(
            case(
                (StockPrice.change_percent > 0, StockPrice.change_percent),
                else_=None,
            )
        )
    ).limit(limit)
    gainers_result = await db.execute(gainers_q)
    gainers = [_to_mover(r) for r in gainers_result.all() if float(r.change_percent or 0) > 0]

    # Losers (asc by change_percent)
    losers_q = base.order_by(StockPrice.change_percent.asc()).limit(limit)
    losers_result = await db.execute(losers_q)
    losers = [_to_mover(r) for r in losers_result.all() if float(r.change_percent or 0) < 0]

    # Most active (desc by volume)
    active_q = base.order_by(desc(StockPrice.volume)).limit(limit)
    active_result = await db.execute(active_q)
    most_active = [_to_mover(r) for r in active_result.all()]

    return MarketMoversResponse(
        gainers=gainers[:limit],
        losers=losers[:limit],
        most_active=most_active[:limit],
        date=str(latest_date),
    )


@router.get("/indices")
async def get_market_indices(db: DbSession) -> MarketIndicesResponse:
    """Major market index values. Uses index-tracking ETFs as proxies."""

    # Use well-known ETFs as index proxies
    index_map = {
        "0050.TW": ("TAIEX (0050)", "TW_TWSE"),
        "SPY": ("S&P 500", "US_NYSE"),
        "QQQ": ("NASDAQ 100", "US_NASDAQ"),
        "DIA": ("Dow Jones", "US_NYSE"),
    }

    indices: list[MarketIndex] = []

    for symbol, (name, _market) in index_map.items():
        q = (
            select(StockPrice.close, StockPrice.change, StockPrice.change_percent)
            .join(Stock, Stock.id == StockPrice.stock_id)
            .where(Stock.symbol == symbol)
            .order_by(StockPrice.date.desc())
            .limit(1)
        )
        result = await db.execute(q)
        row = result.first()
        if row:
            indices.append(
                MarketIndex(
                    symbol=symbol,
                    name=name,
                    value=float(row.close or 0),
                    change=float(row.change or 0),
                    change_percent=float(row.change_percent or 0),
                )
            )

    return MarketIndicesResponse(indices=indices)
