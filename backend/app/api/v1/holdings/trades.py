"""Portfolio trade endpoints — /api/v1/holdings/trades.

Spec §5.4 Table 2 + §9. Same `tier_guard + service-layer second line`
pattern as `accounts.py`. Adds `PortfolioInsufficientSharesError` → 422 mapping for
SELL trades that exceed the open-lot total.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._count_providers import trade_count_provider
from app.auth import require_auth
from app.modules.billing.tier_limits import tier_guard
from app.schemas.holdings.trade import (
    TradeCreateRequest,
    TradeResponse,
    TradeUpdateRequest,
)
from app.services.portfolio import PortfolioTradeService
from app.services.portfolio.exceptions import (
    PortfolioInsufficientSharesError,
    PortfolioAccountNotFoundError,
    PortfolioTradeNotFoundError,
    TierLimitExceededError,
)

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/trades",
    response_model=TradeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(
            tier_guard(
                limit_key="max_trades_per_month",
                current_count_provider=trade_count_provider,
            )
        ),
    ],
)
async def create_trade(
    body: TradeCreateRequest,
    db: DbDep,
    user: UserDep,
) -> TradeResponse:
    """Record a BUY or SELL trade.

    Service-layer responsibilities:
      * Tier asserts (`max_trades_per_month` + BUY-only `max_positions`)
      * Insert trade row
      * Apply lot bookkeeping (BUY → new lot; SELL → FIFO consumption)
      * Upsert the materialized position
      * Emit `portfolio_trade_added` audit event
    """
    service = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    try:
        trade = await service.record_trade(
            account_id=body.account_id,
            action=body.action,
            symbol=body.symbol,
            market=body.market,
            qty=body.qty,
            price=body.price,
            fee=body.fee,
            tax=body.tax,
            trade_date=body.trade_date or date_type.today(),
            note=body.note,
        )
    except PortfolioAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except TierLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.limit_exceeded(exc.limit_key),
        ) from exc
    except PortfolioInsufficientSharesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INSUFFICIENT_SHARES,
        ) from exc
    except ValueError as exc:
        # Defensive: service raises ValueError for unsupported action /
        # non-positive qty. Pydantic should catch these first, but keep
        # the translation here so the contract is total.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INVALID_TRADE_INPUT,
        ) from exc
    await db.commit()
    await db.refresh(trade)
    return TradeResponse.model_validate(trade)


@router.get(
    "/trades",
    response_model=list[TradeResponse],
)
async def list_trades(
    db: DbDep,
    user: UserDep,
    account_id: int = Query(..., description="Filter trades by account id"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TradeResponse]:
    """List trades on one of the user's accounts.

    `account_id` is required (not optional): the service / repo pair
    enforces user isolation via JOIN on `portfolio_accounts`, so the
    caller must always tell us which account to scope to.
    """
    service = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    # Verify ownership FIRST so we return 404 for cross-user / unknown
    # account ids instead of a misleading empty list.
    try:
        await service._require_owned_account(account_id)
    except PortfolioAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    rows = await service._trade_repo.list_by_account(
        account_id=account_id,
        user_id=user.id,  # type: ignore[attr-defined]
        limit=limit,
        offset=offset,
    )
    return [TradeResponse.model_validate(r) for r in rows]


@router.get(
    "/trades/{trade_id}",
    response_model=TradeResponse,
)
async def get_trade(
    trade_id: int,
    db: DbDep,
    user: UserDep,
) -> TradeResponse:
    """Fetch one trade; 404 when missing / not owned."""
    service = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    try:
        row = await service._require_owned_trade(trade_id)
    except PortfolioTradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.TRADE_NOT_FOUND,
        ) from exc
    return TradeResponse.model_validate(row)


@router.patch(
    "/trades/{trade_id}",
    response_model=TradeResponse,
)
async def update_trade(
    trade_id: int,
    body: TradeUpdateRequest,
    db: DbDep,
    user: UserDep,
) -> TradeResponse:
    """PATCH a trade and trigger a full lot-chain rebuild.

    Per Q14.4 "全開放" any field may change; the service replays the
    chronological trade log to recompute lots + position.
    """
    service = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    patch = body.model_dump(exclude_unset=True)
    # Map request-side `qty` -> ORM column `quantity` for the repo.
    if "qty" in patch:
        patch["quantity"] = patch.pop("qty")
    try:
        updated = await service.update_trade(trade_id, **patch)
    except PortfolioTradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.TRADE_NOT_FOUND,
        ) from exc
    except PortfolioInsufficientSharesError as exc:
        # PATCH put the lot chain into an impossible state (e.g. lowered
        # a historical BUY's qty so a downstream SELL no longer balances).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INSUFFICIENT_SHARES,
        ) from exc
    await db.commit()
    await db.refresh(updated)
    return TradeResponse.model_validate(updated)


@router.delete(
    "/trades/{trade_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_trade(
    trade_id: int,
    db: DbDep,
    user: UserDep,
) -> dict[str, bool]:
    """Delete a trade and rebuild the affected position."""
    service = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    try:
        await service.delete_trade(trade_id)
    except PortfolioTradeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.TRADE_NOT_FOUND,
        ) from exc
    except PortfolioInsufficientSharesError as exc:
        # Should be impossible at delete (a SELL going away can only
        # reduce demand) but keep the branch for completeness.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INSUFFICIENT_SHARES,
        ) from exc
    await db.commit()
    return {"ok": True}
