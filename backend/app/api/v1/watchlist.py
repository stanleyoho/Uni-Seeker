"""Watchlist CRUD endpoints — WATCH-001 / Plan 4 Task 7.

GET    /api/v1/watchlist          list current user's watchlist
POST   /api/v1/watchlist          add a stock by symbol (Free tier capped at 10)
DELETE /api/v1/watchlist/{symbol} remove a stock by symbol

Free tier is capped at 10 active watchlist items, but only when
``settings.enable_monetization=True`` (consistent with Plan 4's tier
toggle: when monetization is off, all users behave like PRO).

All mutations write an audit_logs row via the shared audit service.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth import require_auth
from app.config import settings
from app.models.enums import UserTier
from app.models.stock import Stock
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.schemas.watchlist import WatchlistAddRequest, WatchlistItemResponse
from app.services.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watchlist", tags=["watchlist"])

FREE_TIER_LIMIT = 10


async def _get_stock_by_symbol(db: AsyncSession, symbol: str) -> Stock:
    stock = (
        await db.execute(select(Stock).where(Stock.symbol == symbol))
    ).scalar_one_or_none()
    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="stock_not_found"
        )
    return stock


@router.get("/", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_auth)],
) -> list[WatchlistItemResponse]:
    """List current user's watchlist entries (joined with stock symbol)."""
    rows = (
        await db.execute(
            select(WatchlistItem, Stock.symbol)
            .join(Stock, Stock.id == WatchlistItem.stock_id)
            .where(WatchlistItem.user_id == current_user.id)
            .order_by(WatchlistItem.created_at.asc())
        )
    ).all()
    return [
        WatchlistItemResponse(
            id=item.id,
            symbol=symbol,
            created_at=item.created_at.isoformat() if item.created_at else "",
        )
        for item, symbol in rows
    ]


@router.post(
    "/",
    response_model=WatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_to_watchlist(
    req: WatchlistAddRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_auth)],
) -> WatchlistItemResponse:
    """Add a stock (by symbol) to the current user's watchlist.

    - 404 if the symbol does not exist in the stocks table.
    - 403 ``watchlist_limit_exceeded`` if Free tier user is at the 10-item cap
      (only enforced when ``settings.enable_monetization=True``).
    - 409 ``watchlist_already_exists`` if the (user, stock) row already exists.
    """
    stock = await _get_stock_by_symbol(db, req.symbol)

    if settings.enable_monetization and current_user.tier == UserTier.FREE:
        existing = await db.scalar(
            select(func.count())
            .select_from(WatchlistItem)
            .where(WatchlistItem.user_id == current_user.id)
        )
        if existing is not None and existing >= FREE_TIER_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="watchlist_limit_exceeded",
            )

    item = WatchlistItem(user_id=current_user.id, stock_id=stock.id)
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="watchlist_already_exists",
        )

    await log_audit_event(
        db,
        action="watchlist_added",
        user_id=current_user.id,
        resource_type="watchlist_item",
        resource_id=str(item.id),
        metadata={"symbol": req.symbol},
    )
    await db.commit()
    await db.refresh(item)
    return WatchlistItemResponse(
        id=item.id,
        symbol=req.symbol,
        created_at=item.created_at.isoformat() if item.created_at else "",
    )


@router.delete("/{symbol}", status_code=status.HTTP_200_OK)
async def remove_from_watchlist(
    symbol: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_auth)],
) -> dict[str, bool]:
    """Remove a stock (by symbol) from the current user's watchlist.

    - 404 if the symbol is unknown OR the user does not have it on watchlist.
    """
    stock = await _get_stock_by_symbol(db, symbol)
    item = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.user_id == current_user.id,
                WatchlistItem.stock_id == stock.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="watchlist_item_not_found",
        )
    removed_id = item.id
    await db.delete(item)
    await log_audit_event(
        db,
        action="watchlist_removed",
        user_id=current_user.id,
        resource_type="watchlist_item",
        resource_id=str(removed_id),
        metadata={"symbol": symbol},
    )
    await db.commit()
    return {"ok": True}
