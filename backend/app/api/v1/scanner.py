"""Signal scanner API endpoints."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.scanner.engine import SignalScanner, StockSignal
from app.modules.strategy import create_default_registry
from app.modules.strategy.registry import StrategyRegistry
from app.schemas.scanner import (
    ScanResponse,
    SignalDetail,
    SignalScanRequest,
    StockSignalResponse,
)

router = APIRouter(prefix="/scanner", tags=["scanner"])

PRICE_LOOKBACK = 60  # number of trading days to fetch per stock


def _get_strategy_registry() -> StrategyRegistry:
    return create_default_registry()


def _stock_signal_to_response(s: StockSignal) -> StockSignalResponse:
    return StockSignalResponse(
        symbol=s.symbol,
        name=s.name,
        composite_action=s.composite_action,
        score=s.score,
        signals=[
            SignalDetail(
                strategy=sig["strategy"],  # type: ignore[arg-type]
                action=sig["action"],  # type: ignore[arg-type]
                strength=sig["strength"],  # type: ignore[arg-type]
                reason=sig["reason"],  # type: ignore[arg-type]
            )
            for sig in s.signals
        ],
    )


async def _fetch_stocks_closes(
    db: AsyncSession,
    symbols: list[str] | None = None,
    lookback: int = PRICE_LOOKBACK,
) -> list[dict[str, object]]:
    """Fetch latest closing prices for stocks, grouped by symbol.

    Returns a list of dicts with keys ``symbol``, ``name``, ``closes``.
    """
    # Build a subquery that ranks prices per stock descending by date,
    # then keep only the most recent `lookback` rows.
    query = (
        select(
            Stock.symbol,
            Stock.name,
            StockPrice.close,
            StockPrice.date,
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .where(Stock.is_active.is_(True))
        .order_by(Stock.symbol, StockPrice.date.asc())
    )

    if symbols:
        query = query.where(Stock.symbol.in_(symbols))

    result = await db.execute(query)
    rows = result.all()

    # Group by symbol, keeping only last `lookback` prices per stock.
    grouped: dict[str, dict[str, object]] = {}
    for symbol, name, close_price, _date in rows:
        entry = grouped.setdefault(symbol, {"symbol": symbol, "name": name, "closes": []})
        closes_list: list[float] = entry["closes"]  # type: ignore[assignment]
        closes_list.append(float(close_price))

    # Trim to last `lookback` entries (data is already date-ascending).
    stocks_data: list[dict[str, object]] = []
    for entry in grouped.values():
        closes_list = entry["closes"]  # type: ignore[assignment]
        entry["closes"] = closes_list[-lookback:]  # type: ignore[index]
        stocks_data.append(entry)

    return stocks_data


@router.post("/scan", response_model=ScanResponse)
async def scan_stocks(
    req: SignalScanRequest,
    db: AsyncSession = Depends(get_db),
    registry: StrategyRegistry = Depends(_get_strategy_registry),
) -> ScanResponse:
    """Run the signal scanner across multiple stocks."""
    stocks_data = await _fetch_stocks_closes(db, symbols=req.symbols)

    if not stocks_data:
        raise HTTPException(status_code=404, detail="No stocks found for the given symbols")

    scanner = SignalScanner(registry)

    # Validate requested strategy keys if provided.
    available_keys = registry.list_keys()
    if req.strategy_keys:
        invalid = set(req.strategy_keys) - set(available_keys)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy keys: {', '.join(sorted(invalid))}. "
                       f"Available: {', '.join(available_keys)}",
            )

    results = scanner.scan_many(stocks_data, strategy_keys=req.strategy_keys)
    limited = results[: req.limit]

    strategies_used = req.strategy_keys or available_keys

    return ScanResponse(
        results=[_stock_signal_to_response(r) for r in limited],
        scan_date=datetime.now(tz=ZoneInfo("Asia/Taipei")).date().isoformat(),
        total_scanned=len(stocks_data),
        strategies_used=strategies_used,
    )


@router.get("/{symbol}", response_model=StockSignalResponse)
async def get_stock_signals(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    registry: StrategyRegistry = Depends(_get_strategy_registry),
    strategy_keys: list[str] | None = Query(default=None),
) -> StockSignalResponse:
    """Get signals for a single stock."""
    stock = await get_stock_or_404(db, symbol)

    stocks_data = await _fetch_stocks_closes(db, symbols=[symbol])

    if not stocks_data:
        raise HTTPException(status_code=404, detail=f"No price data found for '{symbol}'")

    entry = stocks_data[0]
    closes: list[float] = entry["closes"]  # type: ignore[assignment]

    if len(closes) < 2:
        raise HTTPException(status_code=400, detail=f"Insufficient price data for '{symbol}'")

    # Validate strategy keys.
    available_keys = registry.list_keys()
    if strategy_keys:
        invalid = set(strategy_keys) - set(available_keys)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy keys: {', '.join(sorted(invalid))}. "
                       f"Available: {', '.join(available_keys)}",
            )

    scanner = SignalScanner(registry)
    result = scanner.scan_stock(
        symbol=symbol,
        name=stock.name,
        closes=closes,
        strategy_keys=strategy_keys,
    )

    return _stock_signal_to_response(result)
