"""Trade Journal API — /api/v1/journal/"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.journal import (
    AccountGroup,
    AccountGroupMember,
    AllocationRule,
    Position,
    Trade,
    TradeAccount,
)
from app.modules.trade_journal.fifo_engine import InsufficientSharesError
from app.modules.trade_journal.position_sync import apply_buy, apply_sell, apply_split
from app.modules.trade_journal.rebalance import (
    AllocationRuleData,
    PositionData,
    compute_account_alerts,
)
from app.schemas.journal import (
    AccountCreate,
    AccountDetailResponse,
    AccountResponse,
    AlertsResponse,
    AllocationRuleCreate,
    AllocationRuleResponse,
    GroupCreate,
    GroupMemberResponse,
    GroupResponse,
    PositionResponse,
    RebalanceAlert,
    TradeCreate,
    TradeListResponse,
    TradeResponse,
)

router = APIRouter(prefix="/journal", tags=["journal"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(body: AccountCreate, db: DbDep) -> AccountResponse:
    account = TradeAccount(
        name=body.name,
        broker=body.broker,
        market=body.market,
        currency=body.currency,
        description=body.description,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse.model_validate(account)


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(db: DbDep) -> list[AccountResponse]:
    rows = (await db.execute(select(TradeAccount))).scalars().all()
    return [AccountResponse.model_validate(r) for r in rows]


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
async def get_account(account_id: int, db: DbDep) -> AccountDetailResponse:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    positions_rows = (
        await db.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.is_closed.is_(False),
            )
        )
    ).scalars().all()
    return AccountDetailResponse(
        account=AccountResponse.model_validate(account),
        positions=[PositionResponse.model_validate(p) for p in positions_rows],
    )


# ── Trades ────────────────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/trades", response_model=TradeResponse, status_code=201)
async def add_trade(account_id: int, body: TradeCreate, db: DbDep) -> TradeResponse:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    trade = Trade(
        account_id=account_id,
        symbol=body.symbol,
        market=body.market,
        action=body.action,
        date=body.date,
        price=body.price,
        quantity=body.quantity,
        fee=body.fee,
        tax=body.tax,
        trade_fx_rate=body.trade_fx_rate,
        tags=body.tags,
        note=body.note,
    )
    db.add(trade)
    await db.flush()  # get trade.id before position_sync

    try:
        if body.action == "BUY":
            await apply_buy(db, trade, currency=account.currency)
        elif body.action == "SELL":
            await apply_sell(db, trade, currency=account.currency)
        elif body.action == "SPLIT":
            if not body.split_ratio:
                raise HTTPException(
                    status_code=422, detail="split_ratio required for SPLIT action"
                )
            await apply_split(db, trade, split_ratio=body.split_ratio)
        # DIVIDEND: recorded in trades only, no position change
    except InsufficientSharesError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    await db.commit()
    await db.refresh(trade)
    return TradeResponse.model_validate(trade)


@router.get("/accounts/{account_id}/trades", response_model=TradeListResponse)
async def list_trades(
    account_id: int,
    db: DbDep,
    symbol: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TradeListResponse:
    base_stmt = select(Trade).where(Trade.account_id == account_id)
    if symbol:
        base_stmt = base_stmt.where(Trade.symbol == symbol)

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    rows = (
        await db.execute(
            base_stmt
            .order_by(Trade.date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return TradeListResponse(
        total=total,
        items=[TradeResponse.model_validate(r) for r in rows],
    )


# ── Groups ────────────────────────────────────────────────────────────────────

@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(body: GroupCreate, db: DbDep) -> GroupResponse:
    group = AccountGroup(
        name=body.name,
        description=body.description,
        base_currency=body.base_currency,
    )
    db.add(group)
    await db.flush()  # get group.id

    for member in body.members:
        db.add(AccountGroupMember(
            group_id=group.id,
            account_id=member.account_id,
            target_weight=member.target_weight,
        ))

    await db.commit()
    await db.refresh(group)
    return await _build_group_response(db, group)


@router.get("/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: int, db: DbDep) -> GroupResponse:
    group = await db.get(AccountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return await _build_group_response(db, group)


async def _build_group_response(db: AsyncSession, group: AccountGroup) -> GroupResponse:
    members_rows = (
        await db.execute(
            select(AccountGroupMember).where(AccountGroupMember.group_id == group.id)
        )
    ).scalars().all()
    members = []
    for m in members_rows:
        acc = await db.get(TradeAccount, m.account_id)
        members.append(GroupMemberResponse(
            account_id=m.account_id,
            target_weight=m.target_weight,
            account=AccountResponse.model_validate(acc),
        ))
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        base_currency=group.base_currency,
        members=members,
    )


# ── Allocation Rules ──────────────────────────────────────────────────────────

@router.post("/accounts/{account_id}/allocation", response_model=list[AllocationRuleResponse], status_code=201)
async def set_account_allocation(
    account_id: int,
    rules: list[AllocationRuleCreate],
    db: DbDep,
) -> list[AllocationRuleResponse]:
    account = await db.get(TradeAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    for rule_in in rules:
        existing = (
            await db.execute(
                select(AllocationRule).where(
                    AllocationRule.account_id == account_id,
                    AllocationRule.symbol == rule_in.symbol,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.target_weight = rule_in.target_weight
            existing.lower_threshold = rule_in.lower_threshold
            existing.upper_threshold = rule_in.upper_threshold
            existing.is_active = rule_in.is_active
        else:
            db.add(AllocationRule(
                account_id=account_id,
                group_id=None,
                symbol=rule_in.symbol,
                target_weight=rule_in.target_weight,
                lower_threshold=rule_in.lower_threshold,
                upper_threshold=rule_in.upper_threshold,
                is_active=rule_in.is_active,
            ))

    await db.commit()

    rows = (
        await db.execute(
            select(AllocationRule).where(AllocationRule.account_id == account_id)
        )
    ).scalars().all()
    return [AllocationRuleResponse.model_validate(r) for r in rows]


# ── Rebalance Alerts ──────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(db: DbDep) -> AlertsResponse:
    """Return all triggered rebalance alerts across all accounts.

    NOTE: Phase 1 uses total_cost as proxy for market value (no live price feed yet).
    Live market prices will be integrated in a future phase.
    """
    all_alerts: list[RebalanceAlert] = []

    accounts = (await db.execute(select(TradeAccount))).scalars().all()
    for account in accounts:
        rules_rows = (
            await db.execute(
                select(AllocationRule).where(
                    AllocationRule.account_id == account.id,
                    AllocationRule.is_active.is_(True),
                )
            )
        ).scalars().all()
        if not rules_rows:
            continue

        positions_rows = (
            await db.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.is_closed.is_(False),
                )
            )
        ).scalars().all()

        pos_data = [
            PositionData(
                symbol=p.symbol,
                market_value=p.total_cost or Decimal("0"),
            )
            for p in positions_rows
        ]
        total_value = sum(
            (p.market_value for p in pos_data), Decimal("0")
        )

        rule_data = [
            AllocationRuleData(
                symbol=r.symbol,
                target_weight=r.target_weight,
                lower_threshold=r.lower_threshold,
                upper_threshold=r.upper_threshold,
                is_active=r.is_active,
            )
            for r in rules_rows
        ]
        raw_alerts = compute_account_alerts(
            rules=rule_data,
            positions=pos_data,
            total_value=total_value,
        )
        for a in raw_alerts:
            all_alerts.append(RebalanceAlert(
                scope="account",
                scope_id=account.id,
                scope_name=account.name,
                symbol=a.symbol,
                current_weight=a.current_weight,
                target_weight=a.target_weight,
                deviation=a.deviation,
                direction=a.direction,
            ))

    return AlertsResponse(alerts=all_alerts)
