from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry
from app.models.price import StockPrice
from app.modules.low_base.scorer import calculate_low_base_score
from app.modules.indicators.rsi import RSIIndicator
from app.schemas.low_base import LowBaseRankingResponse, LowBaseScoreResponse

router = APIRouter(prefix="/low-base", tags=["low-base"])


@router.get("/scan", response_model=LowBaseRankingResponse)
async def scan_low_base(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, le=100),
    min_data_days: int = Query(default=60),
) -> LowBaseRankingResponse:
    """Scan all stocks and rank by low-base composite score."""
    # Get all symbols with enough data
    symbol_query = (
        select(StockPrice.symbol, func.count(StockPrice.id).label("cnt"))
        .group_by(StockPrice.symbol)
        .having(func.count(StockPrice.id) >= min_data_days)
    )
    result = await db.execute(symbol_query)
    symbols = [(row[0], row[1]) for row in result.all()]

    scores: list[LowBaseScoreResponse] = []
    rsi_calc = RSIIndicator()

    for symbol, count in symbols:
        # Fetch prices
        price_query = (
            select(StockPrice)
            .where(StockPrice.symbol == symbol)
            .order_by(StockPrice.date.asc())
        )
        price_result = await db.execute(price_query)
        prices = list(price_result.scalars().all())

        if not prices:
            continue

        closes = [float(p.close) for p in prices]
        name = symbol  # We'll get name from Stock table if available

        # Get stock name
        from app.models.stock import Stock
        stock_q = await db.execute(select(Stock.name).where(Stock.symbol == symbol))
        stock_row = stock_q.first()
        if stock_row:
            name = stock_row[0]

        # Calculate RSI
        rsi_result = rsi_calc.calculate(closes, period=14)
        rsi_values = rsi_result.values["RSI"]
        current_rsi = None
        for v in reversed(rsi_values):
            if v is not None:
                current_rsi = v
                break

        # Calculate score (simplified — no financial data from DB yet, use price-only)
        score = calculate_low_base_score(
            symbol=symbol,
            name=name,
            closes=closes,
            rsi=current_rsi,
        )

        if not score.disqualified:
            scores.append(LowBaseScoreResponse(
                symbol=score.symbol,
                name=score.name,
                total_score=score.total_score,
                valuation_score=score.valuation_score,
                price_position_score=score.price_position_score,
                quality_score=score.quality_score,
                pe_percentile=score.details.get("pe_percentile"),
                ma240_deviation=score.details.get("ma240_deviation"),
                peg=score.details.get("peg"),
                details=score.details,
            ))

    # Sort by total_score descending
    scores.sort(key=lambda s: s.total_score, reverse=True)

    return LowBaseRankingResponse(
        results=scores[:limit],
        total_scanned=len(symbols),
        total_qualified=len(scores),
    )


@router.get("/{symbol}", response_model=LowBaseScoreResponse)
async def get_stock_low_base_score(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LowBaseScoreResponse:
    """Get low-base score for a single stock."""
    from fastapi import HTTPException

    price_query = (
        select(StockPrice)
        .where(StockPrice.symbol == symbol)
        .order_by(StockPrice.date.asc())
    )
    result = await db.execute(price_query)
    prices = list(result.scalars().all())

    if len(prices) < 20:
        raise HTTPException(status_code=404, detail=f"Insufficient data for '{symbol}'")

    closes = [float(p.close) for p in prices]

    from app.models.stock import Stock
    stock_q = await db.execute(select(Stock.name).where(Stock.symbol == symbol))
    stock_row = stock_q.first()
    name = stock_row[0] if stock_row else symbol

    rsi_result = RSIIndicator().calculate(closes, period=14)
    current_rsi = None
    for v in reversed(rsi_result.values["RSI"]):
        if v is not None:
            current_rsi = v
            break

    score = calculate_low_base_score(
        symbol=symbol, name=name, closes=closes, rsi=current_rsi,
    )

    return LowBaseScoreResponse(
        symbol=score.symbol, name=score.name,
        total_score=score.total_score,
        valuation_score=score.valuation_score,
        price_position_score=score.price_position_score,
        quality_score=score.quality_score,
        pe_percentile=score.details.get("pe_percentile"),
        ma240_deviation=score.details.get("ma240_deviation"),
        peg=score.details.get("peg"),
        details=score.details,
        disqualified=score.disqualified,
        disqualify_reason=score.disqualify_reason,
    )
