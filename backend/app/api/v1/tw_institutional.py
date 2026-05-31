"""TW 三大法人 (Foreign / Trust / Dealer) HTTP surface.

Mounted at ``/api/v1/tw-institutional``. Distinct prefix from the
``/institutional`` 13F namespace and from the legacy
``/institutional/{symbol}`` FinMind passthrough — see
``app/api/v1/institutional/legacy.py`` for context on that older path.

Endpoints
---------
``GET /top-net``
    Leaderboard of top N stocks by net buy or net sell for a date and
    institutional kind. Used by the home page mini-tiles.

``GET /symbol/{symbol}``
    Last N days of three-way net for a single stock. Used by the
    per-stock drill-down (planned).

Defensive behaviour
-------------------
When the DB has no rows for the requested date (early-day, missed
sync, fresh deployment), the top-net endpoint returns an empty list
with a ``message`` hint instead of raising. The frontend can render
an "尚無資料" placeholder cleanly without an error toast.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.tw_institutional import TwInstitutionalNet
from app.schemas.tw_institutional import (
    TwInstitutionalDayRecord,
    TwInstitutionalSymbolResponse,
    TwInstitutionalTopNetResponse,
    TwInstitutionalTopRow,
)

router = APIRouter(prefix="/tw-institutional", tags=["tw-institutional"])

# Maps the URL ``kind`` query param to the ORM column. Held as a dict
# instead of getattr-by-string so a typo in the request fails fast at
# the dispatcher level rather than crashing the SELECT.
_KIND_COLUMN_MAP = {
    "foreign": TwInstitutionalNet.foreign_net,
    "trust": TwInstitutionalNet.trust_net,
    "dealer": TwInstitutionalNet.dealer_net,
    "total": TwInstitutionalNet.total_net,
}

_ALLOWED_KINDS = tuple(_KIND_COLUMN_MAP.keys())
_ALLOWED_DIRECTIONS = ("buy", "sell")


def _parse_date(value: str | None) -> date_cls:
    """Parse an ISO date, defaulting to today (Taipei TZ) on None."""
    if value is None:
        return datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
    try:
        return date_cls.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{value}'. Expected YYYY-MM-DD.",
        ) from exc


async def _resolve_query_date(
    db: AsyncSession,
    requested: date_cls,
) -> date_cls | None:
    """Use the requested date when present in the table; else fall back
    to the most recent date with any rows. Returns None when the table
    is fully empty so the caller can short-circuit to the empty payload.
    """
    has_requested = await db.execute(
        select(func.count(TwInstitutionalNet.id)).where(TwInstitutionalNet.date == requested)
    )
    if (has_requested.scalar_one() or 0) > 0:
        return requested

    latest = await db.execute(select(func.max(TwInstitutionalNet.date)))
    return latest.scalar_one_or_none()


@router.get("/top-net", response_model=TwInstitutionalTopNetResponse)
async def get_top_net(
    db: Annotated[AsyncSession, Depends(get_db)],
    date: str | None = Query(
        default=None,
        description="ISO date (YYYY-MM-DD). Defaults to today (Taipei).",
    ),
    kind: str = Query(
        default="foreign",
        description="foreign | trust | dealer | total",
    ),
    direction: str = Query(
        default="buy",
        description="buy = top net buyers, sell = top net sellers.",
    ),
    limit: int = Query(default=20, ge=1, le=100),
) -> TwInstitutionalTopNetResponse:
    """Top N stocks by net buy or net sell for the given date and kind."""
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {_ALLOWED_KINDS}",
        )
    if direction not in _ALLOWED_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {_ALLOWED_DIRECTIONS}",
        )

    requested_date = _parse_date(date)
    effective_date = await _resolve_query_date(db, requested_date)

    if effective_date is None:
        # Table is empty (fresh deployment, sync never ran, etc.). The
        # contract is "return cleanly, not 500" so the frontend can
        # render an empty-state tile without an error toast.
        return TwInstitutionalTopNetResponse(
            data=[],
            date=requested_date.isoformat(),
            kind=kind,
            direction=direction,
            message="no data — institutional sync has not produced any rows yet",
        )

    column = _KIND_COLUMN_MAP[kind]
    # ORDER BY: ``buy`` wants the most positive nets first, ``sell``
    # wants the most negative first. Either way we exclude zero rows so
    # the leaderboard isn't padded by stocks with no institutional flow.
    if direction == "buy":
        order_clause = desc(column)
        flow_filter = column > 0
    else:
        order_clause = column.asc()
        flow_filter = column < 0

    query = (
        select(
            Stock.symbol,
            Stock.name,
            column.label("net_amount"),
            StockPrice.close.label("close_price"),
            StockPrice.change_percent.label("cp"),
        )
        .join(Stock, Stock.id == TwInstitutionalNet.stock_id)
        # LEFT JOIN price so a missing price doesn't drop the row.
        .join(
            StockPrice,
            (StockPrice.stock_id == TwInstitutionalNet.stock_id)
            & (StockPrice.date == TwInstitutionalNet.date),
            isouter=True,
        )
        .where(
            TwInstitutionalNet.date == effective_date,
            flow_filter,
        )
        .order_by(order_clause)
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    data = [
        TwInstitutionalTopRow(
            symbol=symbol,
            name=name,
            net_amount=int(net_amount),
            price=(str(close_price) if close_price is not None else None),
            change_percent=(str(cp) if cp is not None else None),
        )
        for symbol, name, net_amount, close_price, cp in rows
    ]

    message: str | None = None
    if not data:
        message = f"no data for kind={kind} direction={direction} on {effective_date}"

    return TwInstitutionalTopNetResponse(
        data=data,
        date=effective_date.isoformat(),
        kind=kind,
        direction=direction,
        message=message,
    )


@router.get("/symbol/{symbol}", response_model=TwInstitutionalSymbolResponse)
async def get_symbol_history(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Trailing window length in calendar days.",
    ),
) -> TwInstitutionalSymbolResponse:
    """Return the last N days of three-way net for a single stock."""
    stock = await get_stock_or_404(db, symbol)

    today = datetime.now(tz=ZoneInfo("Asia/Taipei")).date()
    cutoff = today - timedelta(days=days)

    query = (
        select(TwInstitutionalNet)
        .where(
            TwInstitutionalNet.stock_id == stock.id,
            TwInstitutionalNet.date >= cutoff,
        )
        .order_by(TwInstitutionalNet.date.desc())
    )
    result = await db.execute(query)
    rows = list(result.scalars().all())

    data = [
        TwInstitutionalDayRecord(
            date=row.date,
            foreign_net=row.foreign_net,
            trust_net=row.trust_net,
            dealer_net=row.dealer_net,
            total_net=row.total_net,
        )
        for row in rows
    ]

    return TwInstitutionalSymbolResponse(
        symbol=stock.symbol,
        name=stock.name,
        data=data,
    )
