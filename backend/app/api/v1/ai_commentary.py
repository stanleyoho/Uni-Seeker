"""GET /api/v1/stocks/{symbol}/ai-commentary.

Builds a `CommentaryContext` by pulling:
  - latest + prior day prices (for OHLCV + change)
  - 20-day MA and avg volume (computed inline from the price series)
  - RSI / MACD / Bollinger latest values (via indicator registry)
  - sector hot-top-3 context (via the heatmap aggregate logic)

The deterministic composer returns the narrative + confidence + sources.

Cache: Redis, 4h TTL, keyed by `ai-commentary:{symbol}:{date}`.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_indicator_registry, get_stock_or_404
from app.cache import cache_get, cache_set
from app.models.industry import Industry
from app.models.price import StockPrice
from app.models.stock import Stock
from app.modules.ai_commentary import (
    CommentaryContext,
    compose_commentary,
)
from app.modules.indicators.registry import IndicatorRegistry
from app.schemas.ai_commentary import AiCommentaryResponse, CommentarySourceSchema

# 4 hours — narrative depends on EOD data so a same-day re-render
# returns the same answer; the TTL exists to flush stale entries
# after the next day's price tick lands.
_CACHE_TTL_SEC = 4 * 60 * 60

# Hot-top-3 evaluation requires touching the heatmap aggregate; we
# keep it cheap by limiting the candidate industries we score.
_HOT_TOP_N = 3

router = APIRouter(prefix="/stocks", tags=["ai-commentary"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
Registry = Annotated[IndicatorRegistry, Depends(get_indicator_registry)]


def _latest_value(values: list[float | None]) -> float | None:
    """Return the last non-null value in an indicator series."""
    for v in reversed(values):
        if v is not None:
            return float(v)
    return None


async def _hot_sector_rank(
    db: AsyncSession, industry_name: str, target_date: date_type
) -> tuple[bool, int | None, float | None]:
    """Return (is_top3, rank_1based, avg_change_pct) for `industry_name`.

    Cheap implementation: pull avg(change_percent) grouped by industry
    for the target date, rank desc, look up where `industry_name` falls.
    """
    from sqlalchemy import func

    q = (
        select(
            Industry.name.label("industry_name"),
            func.avg(StockPrice.change_percent).label("avg_chg"),
        )
        .join(Stock, Stock.id == StockPrice.stock_id)
        .join(Industry, Industry.id == Stock.industry_id)
        .where(StockPrice.date == target_date)
        .where(StockPrice.change_percent.isnot(None))
        .group_by(Industry.name)
        .order_by(func.avg(StockPrice.change_percent).desc())
    )
    rows = (await db.execute(q)).all()
    for idx, row in enumerate(rows[:_HOT_TOP_N], start=1):
        if row.industry_name == industry_name:
            return True, idx, float(row.avg_chg or 0.0)
    return False, None, None


def _last_indicator(
    registry: IndicatorRegistry,
    name: str,
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> dict[str, float | None]:
    """Compute an indicator and return latest values for each output key."""
    try:
        ind = registry.get(name)
    except KeyError:
        return {}
    kwargs: dict[str, object] = {}
    if name == "KD" and highs is not None and lows is not None:
        kwargs["highs"] = highs
        kwargs["lows"] = lows
    result = ind.calculate(closes, **kwargs)
    return {k: _latest_value(v) for k, v in result.values.items()}


@router.get("/{symbol}/ai-commentary", response_model=AiCommentaryResponse)
async def get_ai_commentary(
    symbol: str,
    db: DbSession,
    registry: Registry,
) -> AiCommentaryResponse:
    """Return today's deterministic AI commentary for a stock.

    Cached for 4h. Falls back gracefully when indicators or sector
    context are unavailable (e.g. short price series, missing industry).
    """
    stock = await get_stock_or_404(db, symbol)

    # Load full price series for indicator calculation. Cap to 250 rows
    # which is plenty for MA20 / RSI / MACD / BB and keeps the query cheap.
    series_q = (
        select(StockPrice)
        .where(StockPrice.stock_id == stock.id)
        .order_by(StockPrice.date.desc())
        .limit(250)
    )
    series_rows = list((await db.execute(series_q)).scalars().all())
    if not series_rows:
        raise HTTPException(status_code=404, detail=f"No price data for '{symbol}'")

    series_rows.reverse()  # ascending date order for indicators
    latest = series_rows[-1]
    prev = series_rows[-2] if len(series_rows) >= 2 else None

    target_date = latest.date

    # ---- Cache lookup -----------------------------------------------------
    cache_key = f"uni:ai-commentary:{symbol}:{target_date.isoformat()}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return AiCommentaryResponse(**cached)

    closes = [float(p.close) for p in series_rows]
    volumes = [int(p.volume or 0) for p in series_rows]

    # MA20 + 20-day average volume — computed inline, no indicator call needed.
    ma20: float | None = None
    avg_vol_20: float | None = None
    if len(closes) >= 20:
        ma20 = sum(closes[-20:]) / 20
        avg_vol_20 = sum(volumes[-20:]) / 20

    # Indicators
    rsi_vals = _last_indicator(registry, "RSI", closes)
    macd_vals = _last_indicator(registry, "MACD", closes)
    bb_vals = _last_indicator(registry, "BB", closes)

    # Industry name lookup
    industry_name: str | None = None
    if stock.industry_id:
        ind_row = await db.execute(select(Industry).where(Industry.id == stock.industry_id))
        ind_obj = ind_row.scalar_one_or_none()
        industry_name = ind_obj.name if ind_obj else None

    # Hot sector check (only when we have an industry attached)
    sector_is_hot = False
    sector_rank: int | None = None
    sector_avg_pct: float | None = None
    if industry_name:
        sector_is_hot, sector_rank, sector_avg_pct = await _hot_sector_rank(
            db, industry_name, target_date
        )

    ctx = CommentaryContext(
        symbol=symbol,
        name=stock.name,
        target_date=target_date,
        open=float(latest.open),
        high=float(latest.high),
        low=float(latest.low),
        close=float(latest.close),
        prev_close=float(prev.close) if prev else None,
        volume=int(latest.volume or 0),
        avg_volume_20=avg_vol_20,
        ma20=ma20,
        rsi=rsi_vals.get("RSI"),
        macd=macd_vals.get("MACD"),
        macd_signal=macd_vals.get("signal"),
        macd_histogram=macd_vals.get("histogram"),
        bb_upper=bb_vals.get("upper"),
        bb_lower=bb_vals.get("lower"),
        bb_middle=bb_vals.get("middle"),
        industry=industry_name,
        sector_is_hot_top3=sector_is_hot,
        sector_rank=sector_rank,
        sector_avg_change_pct=sector_avg_pct,
        # K8 (PR #114) will flip this to True and populate `patterns`.
        patterns_module_available=False,
        patterns=[],
    )

    narrative, confidence, sources = compose_commentary(ctx)

    response = AiCommentaryResponse(
        symbol=symbol,
        date=target_date,
        commentary=narrative,
        confidence=confidence,
        sources=[CommentarySourceSchema(kind=s.kind, detail=s.detail) for s in sources],
    )

    # ---- Cache write ------------------------------------------------------
    await cache_set(cache_key, response.model_dump(mode="json"), ttl=_CACHE_TTL_SEC)
    return response


# Re-export Taipei tz for tests that need to mint "today" identically.
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
