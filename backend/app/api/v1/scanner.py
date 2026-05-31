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
from app.modules.scanner.patterns import detect_patterns, pattern_names
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


def _stock_signal_to_response(
    s: StockSignal,
    candlestick_patterns: list[str] | None = None,
) -> StockSignalResponse:
    return StockSignalResponse(
        symbol=s.symbol,
        name=s.name,
        composite_action=s.composite_action,
        score=s.score,
        signals=[
            SignalDetail(
                strategy=sig["strategy"],
                action=sig["action"],
                strength=sig["strength"],
                reason=sig["reason"],
            )
            for sig in s.signals
        ],
        candlestick_patterns=candlestick_patterns or [],
    )


async def _fetch_stocks_ohlc(
    db: AsyncSession,
    symbols: list[str] | None = None,
    lookback: int = PRICE_LOOKBACK,
) -> list[dict[str, object]]:
    """Fetch latest OHLC prices for stocks, grouped by symbol.

    Returns a list of dicts with keys ``symbol``, ``name``, ``closes``,
    ``opens``, ``highs``, ``lows``. The strategy scanner only needs
    ``closes``; the candlestick pattern detector needs all four OHLC
    series (TA-Lib pattern functions take ``open / high / low / close``).
    Fetching all four columns in a single query is cheaper than calling
    twice.
    """
    query = (
        select(
            Stock.symbol,
            Stock.name,
            StockPrice.open,
            StockPrice.high,
            StockPrice.low,
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

    # Group by symbol, keeping all OHLC series. Trim to lookback at the
    # end so each stock contributes 4 lists of equal length.
    grouped: dict[str, dict[str, object]] = {}
    for symbol, name, open_p, high_p, low_p, close_p, _date in rows:
        entry = grouped.setdefault(
            symbol,
            {
                "symbol": symbol,
                "name": name,
                "opens": [],
                "highs": [],
                "lows": [],
                "closes": [],
            },
        )
        # Ignore type-checker about list[float] assignments — dict[str,
        # object] forces casts that don't add safety here.
        opens_list: list[float] = entry["opens"]  # type: ignore[assignment]
        highs_list: list[float] = entry["highs"]  # type: ignore[assignment]
        lows_list: list[float] = entry["lows"]  # type: ignore[assignment]
        closes_list: list[float] = entry["closes"]  # type: ignore[assignment]
        opens_list.append(float(open_p))
        highs_list.append(float(high_p))
        lows_list.append(float(low_p))
        closes_list.append(float(close_p))

    stocks_data: list[dict[str, object]] = []
    for entry in grouped.values():
        for key in ("opens", "highs", "lows", "closes"):
            series: list[float] = entry[key]  # type: ignore[assignment]
            entry[key] = series[-lookback:]
        stocks_data.append(entry)

    return stocks_data


@router.post("/scan", response_model=ScanResponse)
async def scan_stocks(
    req: SignalScanRequest,
    db: AsyncSession = Depends(get_db),
    registry: StrategyRegistry = Depends(_get_strategy_registry),
) -> ScanResponse:
    """Run the signal scanner across multiple stocks.

    Each result row now also carries ``candlestick_patterns: list[str]``
    — TA-Lib candlestick patterns firing on the latest bar. See
    ``app.modules.scanner.patterns.SUPPORTED_PATTERNS`` for the list.
    """
    stocks_data = await _fetch_stocks_ohlc(db, symbols=req.symbols)

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

    # Scanner only needs closes — build a compatible list of dicts.
    scanner_input: list[dict[str, object]] = [
        {"symbol": s["symbol"], "name": s["name"], "closes": s["closes"]} for s in stocks_data
    ]
    results = scanner.scan_many(scanner_input, strategy_keys=req.strategy_keys)
    limited = results[: req.limit]

    # Build a lookup: symbol -> candlestick pattern names firing on
    # latest bar. Precomputed once so the response serializer is O(1).
    pattern_by_symbol: dict[str, list[str]] = {}
    for s in stocks_data:
        symbol: str = s["symbol"]  # type: ignore[assignment]
        opens: list[float] = s["opens"]  # type: ignore[assignment]
        highs: list[float] = s["highs"]  # type: ignore[assignment]
        lows: list[float] = s["lows"]  # type: ignore[assignment]
        closes: list[float] = s["closes"]  # type: ignore[assignment]
        hits = detect_patterns(opens, highs, lows, closes)
        pattern_by_symbol[symbol] = pattern_names(hits)

    strategies_used = req.strategy_keys or available_keys

    return ScanResponse(
        results=[
            _stock_signal_to_response(r, pattern_by_symbol.get(r.symbol, [])) for r in limited
        ],
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
    """Get signals for a single stock, including any candlestick
    patterns firing on the latest bar."""
    stock = await get_stock_or_404(db, symbol)

    stocks_data = await _fetch_stocks_ohlc(db, symbols=[symbol])

    if not stocks_data:
        raise HTTPException(status_code=404, detail=f"No price data found for '{symbol}'")

    entry = stocks_data[0]
    closes: list[float] = entry["closes"]  # type: ignore[assignment]
    opens: list[float] = entry["opens"]  # type: ignore[assignment]
    highs: list[float] = entry["highs"]  # type: ignore[assignment]
    lows: list[float] = entry["lows"]  # type: ignore[assignment]

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

    hits = detect_patterns(opens, highs, lows, closes)
    return _stock_signal_to_response(result, pattern_names(hits))
