from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.finmind.institutional_provider import FinMindInstitutionalProvider
from app.modules.indicators.rsi import RSIIndicator
from app.modules.indicators.talib_wrappers import rsi_last
from app.modules.low_base.batch import compute_low_base_batch
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
    # Get all stock_ids with enough data, along with their symbol/name/sector.
    # LEFT JOIN Industry so stocks with NULL industry_id still surface
    # (sector → None → bucketed under "其他" by the frontend).
    symbol_query = (
        select(
            StockPrice.stock_id,
            Stock.symbol,
            Stock.name,
            Industry.name.label("sector"),
            func.count(StockPrice.id).label("cnt"),
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .join(Industry, Industry.id == Stock.industry_id, isouter=True)
        .group_by(StockPrice.stock_id, Stock.symbol, Stock.name, Industry.name)
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

    # ── Batch-fetch every stock's price history in ONE query ─────────────────
    # Before (audit-flagged): one SELECT per row in `stock_rows` →
    # ~N round-trips for a market scan with N qualifying stocks. On TWSE
    # alone N ≈ 950, so /low-base/scan?limit=20 burnt ~6.8s in DB-roundtrip
    # latency even though the data itself was trivial to fetch.
    #
    # After: single `WHERE stock_id IN (...)` lookup ordered by
    # (stock_id, date asc) plus a Python-side group-by. The query
    # planner uses the existing composite index
    # ``ix_stock_prices_stock_id_date`` to satisfy both the IN-filter
    # and the ORDER BY without an extra sort step.
    stock_ids = [row[0] for row in stock_rows]
    prices_by_stock: dict[int, list[StockPrice]] = {sid: [] for sid in stock_ids}
    if stock_ids:
        batched_prices = await db.execute(
            select(StockPrice)
            .where(StockPrice.stock_id.in_(stock_ids))
            .order_by(StockPrice.stock_id, StockPrice.date.asc())
        )
        for price in batched_prices.scalars().all():
            prices_by_stock[price.stock_id].append(price)

    # Resolve sector per symbol once, so both scan paths share the lookup.
    sector_by_symbol: dict[str, str | None] = {
        symbol: sector for _sid, symbol, _name, sector, _cnt in stock_rows
    }

    if not enhanced:
        # ── Vectorized non-enhanced scan (A2) ────────────────────────────
        # The non-enhanced path is pure CPU: RSI(last) + price-position MA
        # math, no per-symbol I/O. We collect (symbol, name, closes, rsi)
        # for the whole universe and score it in ONE vectorized numpy pass
        # via ``compute_low_base_batch`` instead of a per-symbol Python
        # loop. Output is byte-identical to ``calculate_low_base_score``
        # (asserted in tests/unit/modules/test_low_base_batch.py); this is
        # a perf refactor, not a behavioural change.
        #
        # RSI uses ``rsi_last`` (last value only) rather than the full
        # ``RSIIndicator.calculate`` list build — the scan only reads the
        # latest RSI, and the full-list materialization was the dominant
        # cost in the old loop.
        batch_rows: list[tuple[str, str, list[float], float | None]] = []
        for stock_id, symbol, name, _sector, _count in stock_rows:
            prices = prices_by_stock.get(stock_id, [])
            if not prices:
                continue
            closes = [float(p.close) for p in prices]
            batch_rows.append((symbol, name or symbol, closes, rsi_last(closes, period=14)))

        for b in compute_low_base_batch(batch_rows):
            # Non-enhanced scoring never disqualifies (no eps supplied), so
            # every batch row surfaces — mirrors the scalar path where
            # ``score.disqualified`` is always False on this path.
            scores.append(
                LowBaseScoreResponse(
                    symbol=b.symbol,
                    name=b.name,
                    sector=sector_by_symbol.get(b.symbol),
                    total_score=b.total_score,
                    valuation_score=b.valuation_score,
                    price_position_score=b.price_position_score,
                    quality_score=b.quality_score,
                    institutional_technical_score=None,
                    pe_percentile=b.details.get("pe_percentile"),
                    ma240_deviation=b.details.get("ma240_deviation"),
                    peg=b.details.get("peg"),
                    details=b.details,
                )
            )
    else:
        # ── Enhanced scan: per-symbol I/O-bound path (unchanged) ─────────
        # Each symbol fetches institutional flow (async I/O) and runs the
        # signal scanner; it is I/O-bound, not a CPU-vectorization target,
        # so the per-symbol loop stays.
        assert institutional_provider is not None
        assert scanner is not None
        for stock_id, symbol, name, sector, _count in stock_rows:
            prices = prices_by_stock.get(stock_id, [])

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
                        sector=sector,
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

    # Resolve sector via Industry FK — same lookup as the /scan endpoint
    # uses, so the single-symbol response shape matches scan rows.
    sector: str | None = None
    if stock.industry_id is not None:
        ind_row = await db.execute(select(Industry.name).where(Industry.id == stock.industry_id))
        sector = ind_row.scalar_one_or_none()

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
        sector=sector,
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
