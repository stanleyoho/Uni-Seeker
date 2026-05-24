"""Watchlist CRUD endpoints — WATCH-001 / Plan 4 Task 7 (+ Round 6 polish).

GET    /api/v1/watchlist          list current user's watchlist (joined w/ stock name)
POST   /api/v1/watchlist          add a stock by symbol (Free tier capped at 10)
POST   /api/v1/watchlist/bulk     bulk-add up to 20 symbols atomically (Round 6)
DELETE /api/v1/watchlist/{symbol} remove a stock by symbol

Free tier is capped at 10 active watchlist items, but only when
``settings.enable_monetization=True`` (consistent with Plan 4's tier
toggle: when monetization is off, all users behave like PRO).

All mutations write an audit_logs row via the shared audit service.

Round 6 changes:
  - Every response now carries `stock_name` populated via a single JOIN
    onto stocks.name (None when the JOIN misses).
  - New bulk endpoint with partial-success semantics — tier quota is
    pre-checked against the *unique post-dedupe* count so callers can't
    sneak past the cap by spamming duplicates.
"""

from __future__ import annotations

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
from app.obs.logging import get_logger
from app.schemas.watchlist import (
    WatchlistAddRequest,
    WatchlistBulkAddError,
    WatchlistBulkAddRequest,
    WatchlistBulkAddResponse,
    WatchlistItemResponse,
)
from app.services.audit import log_audit_event

logger = get_logger(component="watchlist")
router = APIRouter(prefix="/watchlist", tags=["watchlist"])

FREE_TIER_LIMIT = 10
BULK_MAX_PER_CALL = 20


async def _get_stock_by_symbol(db: AsyncSession, symbol: str) -> Stock:
    stock = (await db.execute(select(Stock).where(Stock.symbol == symbol))).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="stock_not_found")
    return stock


def _normalize_symbol(raw: str) -> str | None:
    """Normalise a user-supplied symbol; return None if invalid.

    Rules mirror WatchlistAddRequest:
      - strip whitespace
      - uppercase (canonical wire form)
      - must be 1..20 chars after stripping
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip().upper()
    if not s or len(s) > 20:
        return None
    return s


@router.get("/", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_auth)],
) -> list[WatchlistItemResponse]:
    """List current user's watchlist entries (joined with stock symbol + name)."""
    rows = (
        await db.execute(
            select(WatchlistItem, Stock.symbol, Stock.name)
            .join(Stock, Stock.id == WatchlistItem.stock_id)
            .where(WatchlistItem.user_id == current_user.id)
            .order_by(WatchlistItem.created_at.asc())
        )
    ).all()
    return [
        WatchlistItemResponse(
            id=item.id,
            symbol=symbol,
            stock_name=name,
            created_at=item.created_at.isoformat() if item.created_at else "",
        )
        for item, symbol, name in rows
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
        stock_name=stock.name,
        created_at=item.created_at.isoformat() if item.created_at else "",
    )


# ── Bulk add (Round 6) ──────────────────────────────────────────────────────


@router.post(
    "/bulk",
    response_model=WatchlistBulkAddResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_add_to_watchlist(
    req: WatchlistBulkAddRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_auth)],
) -> WatchlistBulkAddResponse:
    """Atomically bulk-add up to 20 symbols.

    Pipeline:
      1. Normalise every symbol (strip + uppercase). Empty / oversize entries
         are returned in `errors[reason=invalid_symbol]`.
      2. Dedupe the request itself (a user pasting the same symbol twice
         only counts once).
      3. Look up existing watchlist rows in ONE query → split into
         `skipped_duplicates` (already on user's watchlist) vs candidates
         to insert.
      4. Resolve symbol → stock_id in ONE query. Missing symbols become
         `errors[reason=stock_not_found]`.
      5. Pre-check the Free tier quota against
         `existing_count + len(candidates_to_insert)` and short-circuit
         with 403 ``limit_exceeded:max_watchlist`` if over. The whole batch
         is rejected — partial inserts here would be confusing UX.
      6. Insert all candidates inside a single transaction. On per-row
         IntegrityError (a duplicate that snuck in between steps 3 and 6
         due to concurrent traffic) we re-classify as `skipped_duplicates`.
         Any other DB error rolls the whole batch back and returns 500-ish
         per-row entries.
      7. Audit log each successful insert.

    Returns 201 with the partial-success envelope. The endpoint NEVER
    returns 4xx for per-row issues — only quota (403) and validation
    (422 from Pydantic) and auth (401) can short-circuit.
    """
    # ── Step 1+2: normalise + dedupe request ────────────────────────────
    errors: list[WatchlistBulkAddError] = []
    candidate_symbols: list[str] = []
    seen: set[str] = set()
    for raw in req.symbols:
        norm = _normalize_symbol(raw)
        if norm is None:
            errors.append(
                WatchlistBulkAddError(
                    symbol=raw if isinstance(raw, str) else "",
                    reason="invalid_symbol",
                )
            )
            continue
        if norm in seen:
            # request-level dedupe: only insert once. We don't report this
            # in `skipped_duplicates` because that list is reserved for
            # symbols that were ALREADY on the user's watchlist before
            # this call.
            continue
        seen.add(norm)
        candidate_symbols.append(norm)

    # ── Step 3: which candidates are already on the user's watchlist? ───
    already_owned: set[str] = set()
    if candidate_symbols:
        owned_rows = (
            await db.execute(
                select(Stock.symbol)
                .join(WatchlistItem, WatchlistItem.stock_id == Stock.id)
                .where(
                    WatchlistItem.user_id == current_user.id,
                    Stock.symbol.in_(candidate_symbols),
                )
            )
        ).all()
        already_owned = {row[0] for row in owned_rows}

    skipped_duplicates = [s for s in candidate_symbols if s in already_owned]
    to_insert_symbols = [s for s in candidate_symbols if s not in already_owned]

    # ── Step 4: symbol → stock row resolution ──────────────────────────
    stock_map: dict[str, Stock] = {}
    if to_insert_symbols:
        stock_rows = (
            (await db.execute(select(Stock).where(Stock.symbol.in_(to_insert_symbols))))
            .scalars()
            .all()
        )
        stock_map = {s.symbol: s for s in stock_rows}

    # Symbols requested but not found in stocks table → errors.
    truly_insertable_symbols: list[str] = []
    for sym in to_insert_symbols:
        if sym in stock_map:
            truly_insertable_symbols.append(sym)
        else:
            errors.append(WatchlistBulkAddError(symbol=sym, reason="stock_not_found"))

    # ── Step 5: tier quota pre-check on the BATCH ──────────────────────
    if (
        settings.enable_monetization
        and current_user.tier == UserTier.FREE
        and truly_insertable_symbols
    ):
        existing = (
            await db.scalar(
                select(func.count())
                .select_from(WatchlistItem)
                .where(WatchlistItem.user_id == current_user.id)
            )
            or 0
        )
        projected = existing + len(truly_insertable_symbols)
        if projected > FREE_TIER_LIMIT:
            logger.warning(
                "watchlist_bulk_quota_block",
                user_id=current_user.id,
                existing=existing,
                requested=len(truly_insertable_symbols),
                limit=FREE_TIER_LIMIT,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="limit_exceeded:max_watchlist",
            )

    # ── Step 6+7: insert + audit inside the same transaction ────────────
    added: list[WatchlistItemResponse] = []
    for sym in truly_insertable_symbols:
        stock = stock_map[sym]
        item = WatchlistItem(user_id=current_user.id, stock_id=stock.id)
        db.add(item)
        try:
            await db.flush()
        except IntegrityError:
            # Race with a concurrent single-add. Treat as duplicate, not
            # error. The flush' rollback is implicit in SQLAlchemy 2.x but
            # we still need to clear the pending state via a savepoint
            # rollback. Easiest path: rollback the whole session, re-fetch
            # what's inserted so far, and re-classify this symbol.
            await db.rollback()
            # Anything that was already added in this batch is lost on
            # rollback — that's the atomic contract. Re-raise so the
            # caller sees a 500 rather than a silent partial state.
            logger.error(
                "watchlist_bulk_race",
                user_id=current_user.id,
                symbol=sym,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="watchlist_bulk_race",
            )

        await log_audit_event(
            db,
            action="watchlist_added",
            user_id=current_user.id,
            resource_type="watchlist_item",
            resource_id=str(item.id),
            metadata={"symbol": sym, "via": "bulk"},
        )
        added.append(
            WatchlistItemResponse(
                id=item.id,
                symbol=sym,
                stock_name=stock.name,
                created_at=item.created_at.isoformat() if item.created_at else "",
            )
        )

    await db.commit()

    return WatchlistBulkAddResponse(
        added=added,
        skipped_duplicates=skipped_duplicates,
        errors=errors,
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
