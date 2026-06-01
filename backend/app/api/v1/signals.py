"""Recent-signals API — feeds the home page pre-market signal board.

``GET /signals/recent?lookback_hours=20&top=10``

Data source: ``signal_fires`` (one row per BUY/SELL strategy firing).
The scanner persists into this table on every ``/scanner/scan`` call;
the dashboard reads from it.

The endpoint deduplicates by (symbol, signal_type) within the lookback
window — repeated scans of the same stock within minutes shouldn't
triple-count the same fire. Latest fire wins.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.price import StockPrice
from app.models.signal_fire import SignalFire
from app.models.stock import Stock
from app.schemas.signals import RecentSignalRow, RecentSignalsResponse

router = APIRouter(prefix="/signals", tags=["signals"])

# Map strategy registry keys → home tile signal_type names. Anything
# not in this map is passed through as-is (so an experimental strategy
# still renders, just under its raw key).
_REGISTRY_TO_TILE: dict[str, str] = {
    "ma_crossover": "golden_cross",
    "macd_crossover": "macd_bullish_cross",
    "rsi_oversold": "rsi_oversold_bounce",
    "rsi_bias_combo": "rsi_oversold_bounce",
    "bollinger_bounce": "bollinger_bounce",
    "bias_reversal": "bias_reversal",
}


def _normalize_signal_type(raw: str) -> str:
    """Translate registry key into the home-tile surface name."""
    return _REGISTRY_TO_TILE.get(raw, raw)


@router.get("/recent", response_model=RecentSignalsResponse)
async def get_recent_signals(
    db: Annotated[AsyncSession, Depends(get_db)],
    lookback_hours: int = Query(
        default=20,
        ge=1,
        le=168,
        description="Window in hours measured back from now (UTC).",
    ),
    top: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Max number of signal rows to return.",
    ),
) -> RecentSignalsResponse:
    """Return the most recent BUY signals fired within ``lookback_hours``."""
    cutoff = datetime.now(tz=UTC) - timedelta(hours=lookback_hours)

    # De-duplicate by (symbol, signal_type) — keep the most recent fire.
    # SQLite + PG both support GROUP BY + MAX(fired_at) for this.
    dedup_subq = (
        select(
            SignalFire.symbol,
            SignalFire.signal_type,
            func.max(SignalFire.fired_at).label("latest_fired_at"),
        )
        .where(
            SignalFire.fired_at >= cutoff,
            SignalFire.action == "BUY",
        )
        .group_by(SignalFire.symbol, SignalFire.signal_type)
        .subquery()
    )

    # Join back to SignalFire to recover name + price for the latest fire.
    # LEFT JOIN StockPrice gives us the freshest close + change_percent
    # for the symbol; if a price is missing the row still renders.
    latest_price_subq = select(
        StockPrice.stock_id,
        StockPrice.close,
        StockPrice.change_percent,
        func.row_number()
        .over(
            partition_by=StockPrice.stock_id,
            order_by=desc(StockPrice.date),
        )
        .label("rn"),
    ).subquery()

    query = (
        select(
            SignalFire.symbol,
            SignalFire.name,
            SignalFire.signal_type,
            SignalFire.fired_at,
            latest_price_subq.c.close,
            latest_price_subq.c.change_percent,
        )
        .join(
            dedup_subq,
            (SignalFire.symbol == dedup_subq.c.symbol)
            & (SignalFire.signal_type == dedup_subq.c.signal_type)
            & (SignalFire.fired_at == dedup_subq.c.latest_fired_at),
        )
        .join(Stock, Stock.symbol == SignalFire.symbol, isouter=True)
        .join(
            latest_price_subq,
            (latest_price_subq.c.stock_id == Stock.id) & (latest_price_subq.c.rn == 1),
            isouter=True,
        )
        .order_by(desc(SignalFire.fired_at))
        .limit(top)
    )

    result = await db.execute(query)
    rows = result.all()

    signals = [
        RecentSignalRow(
            symbol=symbol,
            name=name,
            signal_type=_normalize_signal_type(signal_type),
            fired_at=fired_at,
            current_price=(str(close) if close is not None else None),
            change_percent=(str(cp) if cp is not None else None),
        )
        for symbol, name, signal_type, fired_at, close, cp in rows
    ]

    # Grouped counts: total unique (symbol, signal_type) per signal_type
    # within the lookback window — independent of the ``top`` cap, since
    # the home tiles show the total count not the truncated list size.
    grouped_q = await db.execute(
        select(
            dedup_subq.c.signal_type,
            func.count().label("cnt"),
        ).group_by(dedup_subq.c.signal_type)
    )
    grouped: dict[str, int] = {}
    for raw_type, cnt in grouped_q.all():
        tile_name = _normalize_signal_type(raw_type)
        # Multiple raw types can map to one tile_name (rsi_oversold +
        # rsi_bias_combo → "rsi_oversold_bounce"); sum, don't overwrite.
        grouped[tile_name] = grouped.get(tile_name, 0) + int(cnt)

    return RecentSignalsResponse(signals=signals, grouped=grouped)
