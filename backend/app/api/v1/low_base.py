from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.finmind.institutional_provider import FinMindInstitutionalProvider
from app.modules.indicators.rsi import RSIIndicator
from app.modules.low_base.scorer import calculate_low_base_score
from app.modules.scanner.engine import SignalScanner
from app.modules.strategy import create_default_registry as create_strategy_registry
from app.obs.logging import get_logger
from app.schemas.low_base import LowBaseRankingResponse, LowBaseScoreResponse

logger = get_logger(component="low_base")

router = APIRouter(prefix="/low-base", tags=["low-base"])

# ---------------------------------------------------------------------------
# Enhanced-mode helpers
# ---------------------------------------------------------------------------

# Category mapping mirrors app.api.v1.institutional._CATEGORY_MAP
_CATEGORY_MAP: dict[str, str] = {
    "Foreign_Investor": "foreign",
    "Investment_Trust": "trust",
    "Dealer_self": "dealer",
    "Dealer_Hedging": "dealer",
}


def _aggregate_5d_net(raw: list[dict[str, Any]]) -> dict[str, float]:
    """Sum net buy amounts per institutional category over raw records.

    Returns dict with keys ``foreign_net``, ``trust_net``, ``dealer_net``.
    """
    totals: dict[str, float] = {"foreign_net": 0.0, "trust_net": 0.0, "dealer_net": 0.0}
    for row in raw:
        cat = _CATEGORY_MAP.get(row.get("name", ""))
        if cat is None:
            continue
        buy = float(row.get("buy", 0))
        sell = float(row.get("sell", 0))
        totals[f"{cat}_net"] += buy - sell
    return totals


def _scanner_score_to_100(score: float) -> float:
    """Convert scanner composite score (-1..+1) to 0-100 range."""
    return max(0.0, min(100.0, (score + 1.0) * 50.0))


@router.get("/scan", response_model=LowBaseRankingResponse)
async def scan_low_base(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=20, le=100),
    min_data_days: int = Query(default=60),
    enhanced: bool = Query(default=False, description="Enable institutional + technical scoring"),
) -> LowBaseRankingResponse:
    """Scan all stocks and rank by low-base composite score.

    When *enhanced=True*, institutional flow and technical signal data are
    fetched for each stock and fed into the scorer with adjusted weights.
    """
    # Get all stock_ids with enough data, along with their symbol/name
    symbol_query = (
        select(
            StockPrice.stock_id,
            Stock.symbol,
            Stock.name,
            func.count(StockPrice.id).label("cnt"),
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .group_by(StockPrice.stock_id, Stock.symbol, Stock.name)
        .having(func.count(StockPrice.id) >= min_data_days)
    )
    result = await db.execute(symbol_query)
    stock_rows = result.all()

    scores: list[LowBaseScoreResponse] = []
    rsi_calc = RSIIndicator()

    # Prepare enhanced-mode helpers once (outside loop)
    institutional_provider: FinMindInstitutionalProvider | None = None
    scanner: SignalScanner | None = None
    if enhanced:
        institutional_provider = FinMindInstitutionalProvider()
        scanner = SignalScanner(create_strategy_registry())

    # Date range for institutional data (last ~5 trading days = 10 calendar days)
    today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
    inst_start = (today - timedelta(days=10)).isoformat()
    inst_end = today.isoformat()

    for stock_id, symbol, name, _count in stock_rows:
        # Fetch prices
        price_query = (
            select(StockPrice)
            .where(StockPrice.stock_id == stock_id)
            .order_by(StockPrice.date.asc())
        )
        price_result = await db.execute(price_query)
        prices = list(price_result.scalars().all())

        if not prices:
            continue

        closes = [float(p.close) for p in prices]
        display_name = name or symbol

        # Calculate RSI
        rsi_result = rsi_calc.calculate(closes, period=14)
        rsi_values = rsi_result.values["RSI"]
        current_rsi = None
        for v in reversed(rsi_values):
            if v is not None:
                current_rsi = v
                break

        # Enhanced-mode: fetch institutional + technical data
        extra_kwargs: dict[str, float | None] = {}
        if enhanced and institutional_provider is not None and scanner is not None:
            # --- Institutional flow ---
            try:
                raw_symbol = symbol.replace(".TW", "").replace(".TWO", "")
                raw_inst = await institutional_provider.fetch_institutional(
                    stock_id=raw_symbol,
                    start_date=inst_start,
                    end_date=inst_end,
                )
                if raw_inst:
                    nets = _aggregate_5d_net(raw_inst)
                    extra_kwargs["foreign_net_buy_5d"] = nets["foreign_net"]
                    extra_kwargs["trust_net_buy_5d"] = nets["trust_net"]
                    extra_kwargs["dealer_net_buy_5d"] = nets["dealer_net"]
            except Exception:
                logger.warning(
                    "Failed to fetch institutional data for %s, skipping enhancement",
                    symbol,
                    exc_info=True,
                )

            # --- Technical signal score ---
            try:
                if len(closes) >= 2:
                    signal_result = scanner.scan_stock(
                        symbol=symbol,
                        name=display_name,
                        closes=closes,
                    )
                    extra_kwargs["technical_score"] = _scanner_score_to_100(
                        signal_result.score,
                    )
            except Exception:
                logger.warning(
                    "Failed to run signal scanner for %s, skipping enhancement",
                    symbol,
                    exc_info=True,
                )

        # Calculate score
        score = calculate_low_base_score(
            symbol=symbol,
            name=display_name,
            closes=closes,
            rsi=current_rsi,
            **extra_kwargs,  # type: ignore[arg-type]
        )

        if not score.disqualified:
            scores.append(
                LowBaseScoreResponse(
                    symbol=score.symbol,
                    name=score.name,
                    total_score=score.total_score,
                    valuation_score=score.valuation_score,
                    price_position_score=score.price_position_score,
                    quality_score=score.quality_score,
                    institutional_technical_score=score.institutional_technical_score,
                    pe_percentile=score.details.get("pe_percentile"),
                    ma240_deviation=score.details.get("ma240_deviation"),
                    peg=score.details.get("peg"),
                    details=score.details,
                )
            )

    # Sort by total_score descending
    scores.sort(key=lambda s: s.total_score, reverse=True)

    return LowBaseRankingResponse(
        results=scores[:limit],
        total_scanned=len(stock_rows),
        total_qualified=len(scores),
    )


@router.get("/{symbol}", response_model=LowBaseScoreResponse)
async def get_stock_low_base_score(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    enhanced: bool = Query(default=False, description="Enable institutional + technical scoring"),
) -> LowBaseScoreResponse:
    """Get low-base score for a single stock.

    When *enhanced=True*, institutional flow and technical signal data are
    fetched and incorporated into the composite score.
    """
    stock = await get_stock_or_404(db, symbol)

    price_query = (
        select(StockPrice).where(StockPrice.stock_id == stock.id).order_by(StockPrice.date.asc())
    )
    result = await db.execute(price_query)
    prices = list(result.scalars().all())

    if len(prices) < 20:
        raise HTTPException(status_code=404, detail=f"Insufficient data for '{symbol}'")

    closes = [float(p.close) for p in prices]
    name = stock.name or symbol

    rsi_result = RSIIndicator().calculate(closes, period=14)
    current_rsi = None
    for v in reversed(rsi_result.values["RSI"]):
        if v is not None:
            current_rsi = v
            break

    # Enhanced-mode: fetch institutional + technical data
    extra_kwargs: dict[str, float | None] = {}
    if enhanced:
        today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
        inst_start = (today - timedelta(days=10)).isoformat()
        inst_end = today.isoformat()

        # --- Institutional flow ---
        try:
            provider = FinMindInstitutionalProvider()
            raw_symbol = symbol.replace(".TW", "").replace(".TWO", "")
            raw_inst = await provider.fetch_institutional(
                stock_id=raw_symbol,
                start_date=inst_start,
                end_date=inst_end,
            )
            if raw_inst:
                nets = _aggregate_5d_net(raw_inst)
                extra_kwargs["foreign_net_buy_5d"] = nets["foreign_net"]
                extra_kwargs["trust_net_buy_5d"] = nets["trust_net"]
                extra_kwargs["dealer_net_buy_5d"] = nets["dealer_net"]
        except Exception:
            logger.warning(
                "Failed to fetch institutional data for %s",
                symbol,
                exc_info=True,
            )

        # --- Technical signal score ---
        try:
            if len(closes) >= 2:
                scanner = SignalScanner(create_strategy_registry())
                signal_result = scanner.scan_stock(
                    symbol=symbol,
                    name=name,
                    closes=closes,
                )
                extra_kwargs["technical_score"] = _scanner_score_to_100(
                    signal_result.score,
                )
        except Exception:
            logger.warning(
                "Failed to run signal scanner for %s",
                symbol,
                exc_info=True,
            )

    score = calculate_low_base_score(
        symbol=symbol,
        name=name,
        closes=closes,
        rsi=current_rsi,
        **extra_kwargs,  # type: ignore[arg-type]
    )

    return LowBaseScoreResponse(
        symbol=score.symbol,
        name=score.name,
        total_score=score.total_score,
        valuation_score=score.valuation_score,
        price_position_score=score.price_position_score,
        quality_score=score.quality_score,
        institutional_technical_score=score.institutional_technical_score,
        pe_percentile=score.details.get("pe_percentile"),
        ma240_deviation=score.details.get("ma240_deviation"),
        peg=score.details.get("peg"),
        details=score.details,
        disqualified=score.disqualified,
        disqualify_reason=score.disqualify_reason,
    )
