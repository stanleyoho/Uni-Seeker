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

# Upper bound on `_fetch_stocks_closes` when the caller does NOT pass an
# explicit ``symbols`` list. Audit-flagged: a bare POST /scanner/scan
# with no symbols previously fanned out to every active stock (~1500
# rows × 60-day lookback ≈ 90k Decimal rows). The bound below caps the
# work at ~300 stocks worth of price history per request, which still
# covers TWSE-50 + main US large-caps in one call but stops a curious
# user from accidentally OOM-ing the worker.
#
# Tuning rationale: 300 × 60 ≈ 18k rows, ~50 ms on a warm cache locally.
# Raise if a future use-case needs broader coverage; lower if WS scan
# subscriptions start showing latency in the dashboard.
DEFAULT_SCAN_MAX_STOCKS = 300


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
                strategy=sig["strategy"],
                action=sig["action"],
                strength=sig["strength"],
                reason=sig["reason"],
            )
            for sig in s.signals
        ],
    )


async def _fetch_stocks_closes(
    db: AsyncSession,
    symbols: list[str] | None = None,
    lookback: int = PRICE_LOOKBACK,
    max_stocks: int = DEFAULT_SCAN_MAX_STOCKS,
) -> list[dict[str, object]]:
    """Fetch latest closing prices for stocks, grouped by symbol.

    Returns a list of dicts with keys ``symbol``, ``name``, ``closes``.

    When ``symbols`` is omitted the query is bounded to the most
    recently-updated ``max_stocks`` active rows so a bare scan request
    can't fan out across the entire universe (audit fix). The
    ``is_active`` filter benefits from the ``ix_stocks_is_active``
    index added in UNI-PERF-001; the symbol IN-clause uses the existing
    unique index on ``symbol``.
    """
    # Resolve the candidate stock set first so the price query can use a
    # cheap IN-clause on the indexed ``stock_id`` column rather than a
    # 2-table join across the whole universe.
    candidate_query = select(Stock.id, Stock.symbol, Stock.name).where(Stock.is_active.is_(True))
    if symbols:
        candidate_query = candidate_query.where(Stock.symbol.in_(symbols))
    else:
        # Apply the upper bound only when the caller did NOT enumerate
        # symbols explicitly — caller-provided lists are honoured as-is
        # so single-stock probes never get silently truncated.
        candidate_query = candidate_query.order_by(Stock.updated_at.desc()).limit(max_stocks)

    candidate_rows = (await db.execute(candidate_query)).all()
    if not candidate_rows:
        return []

    id_to_meta: dict[int, tuple[str, str]] = {sid: (sym, name) for sid, sym, name in candidate_rows}

    # Pull every price row for the candidate set in ONE query. The
    # composite index ``ix_stock_prices_stock_id_date`` services both the
    # IN-filter and the ORDER BY without a sort step.
    query = (
        select(StockPrice.stock_id, StockPrice.close, StockPrice.date)
        .where(StockPrice.stock_id.in_(list(id_to_meta.keys())))
        .order_by(StockPrice.stock_id, StockPrice.date.asc())
    )
    result = await db.execute(query)
    raw_rows = result.all()
    # Re-shape into the legacy (symbol, name, close, date) row tuples so
    # the grouping block below stays unchanged.
    rows = [
        (id_to_meta[stock_id][0], id_to_meta[stock_id][1], close_price, _date)
        for stock_id, close_price, _date in raw_rows
        if stock_id in id_to_meta
    ]

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
        entry["closes"] = closes_list[-lookback:]
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
