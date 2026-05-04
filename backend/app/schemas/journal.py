"""Pydantic schemas for Trade Journal API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ── Account ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str
    broker: str | None = None
    market: Literal["TW", "US", "CRYPTO"]
    currency: Literal["TWD", "USD", "USDT", "BTC", "ETH"]
    description: str | None = None


class AccountResponse(BaseModel):
    id: int
    name: str
    broker: str | None
    market: str
    currency: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Trade ─────────────────────────────────────────────────────────────────────

class TradeCreate(BaseModel):
    symbol: str
    market: Literal["TW", "US", "CRYPTO"]
    action: Literal["BUY", "SELL", "DIVIDEND", "SPLIT"]
    date: date
    price: Decimal | None = None
    quantity: Decimal | None = None
    fee: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    trade_fx_rate: Decimal | None = None
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    split_ratio: Decimal | None = None  # For SPLIT: new_shares / old_shares (e.g. 2.0 for 2:1)


class TradeResponse(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    action: str
    date: date
    price: Decimal | None
    quantity: Decimal | None
    fee: Decimal
    tax: Decimal
    trade_fx_rate: Decimal | None
    tags: list[str]
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TradeListResponse(BaseModel):
    total: int
    items: list[TradeResponse]


# ── Position ──────────────────────────────────────────────────────────────────

class PositionResponse(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    currency: str
    quantity: Decimal
    avg_cost_fifo: Decimal | None
    total_cost: Decimal | None
    realized_pnl: Decimal
    is_closed: bool

    model_config = {"from_attributes": True}


# ── Account Detail (with positions) ──────────────────────────────────────────

class AccountDetailResponse(BaseModel):
    account: AccountResponse
    positions: list[PositionResponse]


# ── Group ─────────────────────────────────────────────────────────────────────

class GroupMemberInput(BaseModel):
    account_id: int
    target_weight: Decimal | None = None


class GroupCreate(BaseModel):
    name: str
    description: str | None = None
    base_currency: str = "TWD"
    members: list[GroupMemberInput] = Field(default_factory=list)


class GroupMemberResponse(BaseModel):
    account_id: int
    target_weight: Decimal | None
    account: AccountResponse

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: int
    name: str
    description: str | None
    base_currency: str
    members: list[GroupMemberResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ── Allocation Rule ───────────────────────────────────────────────────────────

class AllocationRuleCreate(BaseModel):
    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal = Decimal("0.03")
    upper_threshold: Decimal = Decimal("0.03")
    is_active: bool = True


class AllocationRuleResponse(BaseModel):
    id: int
    symbol: str
    target_weight: Decimal
    lower_threshold: Decimal
    upper_threshold: Decimal
    is_active: bool

    model_config = {"from_attributes": True}


# ── Rebalance Alert ───────────────────────────────────────────────────────────

class RebalanceAlert(BaseModel):
    scope: Literal["account", "group"]
    scope_id: int
    scope_name: str
    symbol: str
    current_weight: Decimal
    target_weight: Decimal
    deviation: Decimal  # current - target (positive = overweight)
    direction: Literal["over", "under"]


class AlertsResponse(BaseModel):
    alerts: list[RebalanceAlert]
