"""Market overview API: indices, movers (gainers/losers/volume)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.cache import cache_get, cache_set, make_cache_key
from app.models.price import StockPrice
from app.models.stock import Stock
from app.schemas.market import (
    MarketIndex,
    MarketIndicesResponse,
    MarketMover,
    MarketMoversResponse,
)

MARKET_CACHE_TTL = 300  # 5 minutes
MIN_INDICES_COUNT = 4
MIN_MOVERS_COUNT = 5

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/market", tags=["market"])


# -- Demo / Fallback Data -----------------------------------------------------


def _demo_indices() -> list[MarketIndex]:
    """Fallback market indices when DB has insufficient data."""
    return [
        MarketIndex(
            symbol="^TWII",
            name="TAIEX (加權指數)",
            value=21345.67,
            change=156.23,
            change_percent=0.74,
        ),
        MarketIndex(
            symbol="SPY",
            name="S&P 500",
            value=5432.10,
            change=28.45,
            change_percent=0.53,
        ),
        MarketIndex(
            symbol="QQQ",
            name="NASDAQ 100",
            value=17856.34,
            change=-45.12,
            change_percent=-0.25,
        ),
        MarketIndex(
            symbol="^SOX",
            name="Philadelphia Semiconductor (費半)",
            value=4523.89,
            change=67.34,
            change_percent=1.51,
        ),
        MarketIndex(
            symbol="DIA",
            name="Dow Jones",
            value=39876.54,
            change=112.67,
            change_percent=0.28,
        ),
        MarketIndex(
            symbol="^TPEX",
            name="OTC Index (櫃買指數)",
            value=215.43,
            change=-1.23,
            change_percent=-0.57,
        ),
    ]


def _demo_movers() -> MarketMoversResponse:
    """Fallback market movers when DB has insufficient data."""
    today = str(datetime.now(tz=ZoneInfo("Asia/Taipei")).date())

    gainers_data = [
        ("2330", "台積電 TSMC", "TW_TWSE", 895.0, 35.0, 4.07, 45230000),
        ("2454", "聯發科 MediaTek", "TW_TWSE", 1285.0, 45.0, 3.63, 12340000),
        ("3661", "世芯-KY", "TW_TWSE", 2150.0, 70.0, 3.37, 3450000),
        ("2382", "廣達 Quanta", "TW_TWSE", 312.0, 9.5, 3.14, 18760000),
        ("6505", "台塑化", "TW_TWSE", 78.5, 2.3, 3.02, 8920000),
        ("3034", "聯詠 Novatek", "TW_TWSE", 525.0, 15.0, 2.94, 6780000),
        ("2303", "聯電 UMC", "TW_TWSE", 52.3, 1.4, 2.75, 32100000),
        ("2881", "富邦金 Fubon", "TW_TWSE", 85.6, 2.2, 2.64, 15670000),
        ("3711", "日月光投控", "TW_TWSE", 158.0, 4.0, 2.60, 9870000),
        ("2412", "中華電 CHT", "TW_TWSE", 132.5, 3.0, 2.32, 5430000),
    ]

    losers_data = [
        ("2317", "鴻海 Foxconn", "TW_TWSE", 142.0, -5.5, -3.73, 28900000),
        ("2603", "長榮 Evergreen", "TW_TWSE", 165.0, -6.0, -3.51, 22100000),
        ("2609", "陽明 Yang Ming", "TW_TWSE", 68.4, -2.3, -3.25, 19870000),
        ("1301", "台塑 FPC", "TW_TWSE", 62.8, -2.0, -3.08, 11230000),
        ("2002", "中鋼 CSC", "TW_TWSE", 25.1, -0.75, -2.90, 35670000),
        ("1303", "南亞", "TW_TWSE", 56.7, -1.6, -2.74, 8900000),
        ("2891", "中信金", "TW_TWSE", 28.9, -0.75, -2.53, 42300000),
        ("3037", "欣興", "TW_TWSE", 178.0, -4.5, -2.47, 7650000),
        ("2912", "統一超", "TW_TWSE", 268.0, -6.0, -2.19, 3210000),
        ("1216", "統一", "TW_TWSE", 72.3, -1.5, -2.03, 6540000),
    ]

    active_data = [
        ("2330", "台積電 TSMC", "TW_TWSE", 895.0, 35.0, 4.07, 45230000),
        ("2891", "中信金", "TW_TWSE", 28.9, -0.75, -2.53, 42300000),
        ("2002", "中鋼 CSC", "TW_TWSE", 25.1, -0.75, -2.90, 35670000),
        ("2303", "聯電 UMC", "TW_TWSE", 52.3, 1.4, 2.75, 32100000),
        ("2317", "鴻海 Foxconn", "TW_TWSE", 142.0, -5.5, -3.73, 28900000),
        ("2603", "長榮 Evergreen", "TW_TWSE", 165.0, -6.0, -3.51, 22100000),
        ("2609", "陽明 Yang Ming", "TW_TWSE", 68.4, -2.3, -3.25, 19870000),
        ("2382", "廣達 Quanta", "TW_TWSE", 312.0, 9.5, 3.14, 18760000),
        ("2881", "富邦金 Fubon", "TW_TWSE", 85.6, 2.2, 2.64, 15670000),
        ("2454", "聯發科 MediaTek", "TW_TWSE", 1285.0, 45.0, 3.63, 12340000),
    ]

    def _make_movers(data: list[tuple[Any, ...]]) -> list[MarketMover]:
        return [
            MarketMover(
                symbol=d[0],
                name=d[1],
                market=d[2],
                close=d[3],
                change=d[4],
                change_percent=d[5],
                volume=d[6],
            )
            for d in data
        ]

    return MarketMoversResponse(
        gainers=_make_movers(gainers_data),
        losers=_make_movers(losers_data),
        most_active=_make_movers(active_data),
        date=today,
    )


# -- Helpers ------------------------------------------------------------------


def _to_mover(row: Any) -> MarketMover:
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

    cache_key = make_cache_key("market:movers", market_filter, limit)
    cached = await cache_get(cache_key)
    if cached:
        return MarketMoversResponse(**cached)

    # Find latest date with data
    latest_q = select(func.max(StockPrice.date))
    if market_filter:
        latest_q = latest_q.join(Stock, Stock.id == StockPrice.stock_id).where(
            Stock.market == market_filter
        )
    latest_result = await db.execute(latest_q)
    latest_date = latest_result.scalar()

    if not latest_date:
        # No DB data at all - return demo data directly
        demo = _demo_movers()
        return MarketMoversResponse(
            gainers=demo.gainers[:limit],
            losers=demo.losers[:limit],
            most_active=demo.most_active[:limit],
            date=demo.date,
        )

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

    # Fallback: if DB has fewer than MIN_MOVERS_COUNT in any category, use demo data
    if (
        len(gainers) < MIN_MOVERS_COUNT
        or len(losers) < MIN_MOVERS_COUNT
        or len(most_active) < MIN_MOVERS_COUNT
    ):
        demo = _demo_movers()
        existing_g = {m.symbol for m in gainers}
        existing_l = {m.symbol for m in losers}
        existing_a = {m.symbol for m in most_active}

        for m in demo.gainers:
            if m.symbol not in existing_g and len(gainers) < limit:
                gainers.append(m)
                existing_g.add(m.symbol)
        for m in demo.losers:
            if m.symbol not in existing_l and len(losers) < limit:
                losers.append(m)
                existing_l.add(m.symbol)
        for m in demo.most_active:
            if m.symbol not in existing_a and len(most_active) < limit:
                most_active.append(m)
                existing_a.add(m.symbol)

        if not latest_date:
            latest_date = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()

    response = MarketMoversResponse(
        gainers=gainers[:limit],
        losers=losers[:limit],
        most_active=most_active[:limit],
        date=str(latest_date),
    )
    await cache_set(cache_key, json.loads(response.model_dump_json()), ttl=MARKET_CACHE_TTL)
    return response


@router.get("/indices")
async def get_market_indices(db: DbSession) -> MarketIndicesResponse:
    """Major market index values. Uses index-tracking ETFs as proxies."""

    cache_key = make_cache_key("market:indices")
    cached = await cache_get(cache_key)
    if cached:
        return MarketIndicesResponse(**cached)

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

    # Fallback: if DB has fewer than MIN_INDICES_COUNT indices, supplement with demo data
    if len(indices) < MIN_INDICES_COUNT:
        existing_symbols = {idx.symbol for idx in indices}
        for demo_idx in _demo_indices():
            if demo_idx.symbol not in existing_symbols:
                indices.append(demo_idx)

    response = MarketIndicesResponse(indices=indices)
    await cache_set(cache_key, json.loads(response.model_dump_json()), ttl=MARKET_CACHE_TTL)
    return response
