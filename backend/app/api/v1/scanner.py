"""Signal scanner API endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.models.signal_fire import SignalFire
from app.models.stock import Stock
from app.modules.scanner.engine import SignalScanner, StockSignal
from app.modules.scanner.patterns import detect_patterns, pattern_names
from app.modules.strategy import create_default_registry
from app.modules.strategy.registry import StrategyRegistry
from app.schemas.best_four_point import BestFourPointResponse, BestFourPointRow
from app.schemas.scanner import (
    ScanResponse,
    SignalDetail,
    SignalScanRequest,
    StockSignalResponse,
)
from app.services.best_four_point import read_cached_scan

logger = structlog.get_logger()

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
    max_stocks: int = DEFAULT_SCAN_MAX_STOCKS,
) -> list[dict[str, object]]:
    """Fetch latest OHLC prices for stocks, grouped by symbol.

    Returns a list of dicts with keys ``symbol``, ``name``, ``closes``,
    ``opens``, ``highs``, ``lows``. The strategy scanner only needs
    ``closes``; the candlestick pattern detector needs all four OHLC
    series (TA-Lib pattern functions take ``open / high / low / close``).
    Fetching all four columns is cheaper than calling twice.

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
    # IN-filter and the ORDER BY without a sort step. All four OHLC columns
    # are fetched because the candlestick pattern detector needs them
    # (TA-Lib pattern functions take open / high / low / close); fetching
    # them here is cheaper than a second round-trip.
    query = (
        select(
            StockPrice.stock_id,
            StockPrice.open,
            StockPrice.high,
            StockPrice.low,
            StockPrice.close,
            StockPrice.date,
        )
        .where(StockPrice.stock_id.in_(list(id_to_meta.keys())))
        .order_by(StockPrice.stock_id, StockPrice.date.asc())
    )
    result = await db.execute(query)
    raw_rows = result.all()
    # Re-shape into (symbol, name, open, high, low, close, date) row tuples
    # so the grouping block below stays unchanged.
    rows = [
        (
            id_to_meta[stock_id][0],
            id_to_meta[stock_id][1],
            open_price,
            high_price,
            low_price,
            close_price,
            _date,
        )
        for stock_id, open_price, high_price, low_price, close_price, _date in raw_rows
        if stock_id in id_to_meta
    ]

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

    # Persist BUY fires to the signal_fires event log so the home page
    # pre-market signal board can read them. Best-effort: a write
    # failure must NOT 500 the scan response (the home board is a
    # convenience surface, the scan API is the primary contract).
    try:
        await _persist_buy_fires(db, results, stocks_data)
    except Exception as exc:  # pragma: no cover - belt-and-suspenders
        logger.warning("signal_fire_persist_failed", error=str(exc))

    return ScanResponse(
        results=[
            _stock_signal_to_response(r, pattern_by_symbol.get(r.symbol, [])) for r in limited
        ],
        scan_date=datetime.now(tz=ZoneInfo("Asia/Taipei")).date().isoformat(),
        total_scanned=len(stocks_data),
        strategies_used=strategies_used,
    )


async def _persist_buy_fires(
    db: AsyncSession,
    results: list[StockSignal],
    stocks_data: list[dict[str, object]],
) -> None:
    """Write one SignalFire row per BUY signal in ``results``.

    Why only BUY: the pre-market signal board is a long-only screener
    (黃金交叉 / 量價突破 / RSI 反彈). SELL signals can be added later
    when there's UI for them. SignalFire is *additive* — we don't
    UPSERT here; a fresh row each scan is fine because the GET endpoint
    deduplicates by (symbol, signal_type) and keeps the latest.
    """
    # Latest close per stock from the prepared stocks_data — saves a
    # second JOIN at write time.
    latest_close: dict[str, float] = {}
    for s in stocks_data:
        sym = s.get("symbol")
        closes = s.get("closes") or []
        if isinstance(sym, str) and closes and isinstance(closes, list):
            latest_close[sym] = float(closes[-1])

    new_rows: list[SignalFire] = []
    for r in results:
        price = latest_close.get(r.symbol)
        for sig in r.signals:
            action = str(sig.get("action", ""))
            if action != "BUY":
                continue
            # ``sig`` is typed ``dict[str, object]`` on StockSignal, so each
            # ``.get()`` returns ``object``. Coerce via ``str()`` first
            # (handles None/0 sentinels) before float() to keep mypy happy.
            raw_strength = sig.get("strength", 0.0)
            strength_val = float(str(raw_strength)) if raw_strength is not None else 0.0
            # SignalFire.fire_price is Mapped[float | None]; the underlying
            # column is Numeric(12,4) so SA accepts float or Decimal at
            # runtime, but the typed surface here is float.
            fire_price_val: float | None = float(Decimal(str(price))) if price is not None else None
            new_rows.append(
                SignalFire(
                    symbol=r.symbol,
                    name=r.name,
                    signal_type=str(sig.get("strategy", "")),
                    action=action,
                    strength=strength_val,
                    fire_price=fire_price_val,
                )
            )

    if new_rows:
        db.add_all(new_rows)
        await db.commit()


@router.get("/best-four-point", response_model=BestFourPointResponse)
async def get_best_four_point(
    db: AsyncSession = Depends(get_db),
) -> BestFourPointResponse:
    """Return today's cached 四大買賣點 (Best Four Buy/Sell Points) scan.

    Reads ONLY the cached results persisted by the daily scheduled scan
    (``best_four_point_scan`` — runs post-close over the full TW universe).
    The endpoint never computes the universe live: 1500+ symbols × MA/volume
    math per request would be far too heavy for an interactive call. When no
    scan has run yet (fresh deploy) it returns an empty result with
    ``scan_date=None`` so the frontend can render an empty state.

    Routing note: this static path is declared BEFORE the ``/{symbol}``
    catch-all so ``best-four-point`` is never swallowed as a stock symbol.
    """
    scan_date, rows = await read_cached_scan(db)

    buy: list[BestFourPointRow] = []
    sell: list[BestFourPointRow] = []
    for row in rows:
        model = BestFourPointRow(
            symbol=str(row.get("symbol", "")),
            name=str(row.get("name", "") or row.get("symbol", "")),
            verdict=str(row.get("verdict", "觀望")),
            buy_points=list(row.get("buy_points", []) or []),
            sell_points=list(row.get("sell_points", []) or []),
            net_score=int(row.get("net_score", 0) or 0),
            last_close=row.get("last_close"),
        )
        # A symbol surfaces on the buy board when it has gated buy points,
        # on the sell board when it has gated sell points. 觀望 / no-signal
        # rows are persisted (for audit) but not surfaced on either board.
        if model.buy_points:
            buy.append(model)
        elif model.sell_points:
            sell.append(model)

    # Buy: strongest net first. Sell: most-negative net first.
    buy.sort(key=lambda r: r.net_score, reverse=True)
    sell.sort(key=lambda r: r.net_score)

    return BestFourPointResponse(
        scan_date=scan_date.isoformat() if scan_date is not None else None,
        buy_signals=buy,
        sell_signals=sell,
        total_scanned=len(rows),
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
