"""SQLAlchemy models for the Trade Journal module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TradeAccount(Base):
    __tablename__ = "trade_accounts"

    # non-default fields first (required by MappedAsDataclass)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)   # TW / US / CRYPTO
    currency: Mapped[str] = mapped_column(String(10), nullable=False)  # TWD / USD / USDT
    # optional / defaulted fields after
    broker: Mapped[str | None] = mapped_column(String(50), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


class AccountGroup(Base):
    __tablename__ = "account_groups"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # optional / defaulted fields after
    description: Mapped[str | None] = mapped_column(Text, default=None)
    base_currency: Mapped[str] = mapped_column(String(10), default="TWD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


class AccountGroupMember(Base):
    __tablename__ = "account_group_members"
    __table_args__ = (UniqueConstraint("group_id", "account_id"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("account_groups.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id", ondelete="CASCADE"), nullable=False
    )
    # optional / defaulted fields after
    target_weight: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), default=None)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_account_symbol", "account_id", "symbol", "market", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY/SELL/DIVIDEND/SPLIT
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # optional / defaulted fields after
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    trade_fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=None)
    tags: Mapped[list[str]] = mapped_column(JSONB, default_factory=list)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )


class TradeLot(Base):
    __tablename__ = "trade_lots"
    __table_args__ = (
        Index(
            "ix_trade_lots_fifo",
            "account_id", "symbol", "market", "is_exhausted", "trade_id",
        ),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    trade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    original_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    # optional / defaulted fields after
    is_exhausted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", "market"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("trade_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    # optional / defaulted fields after
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    avg_cost_fifo: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(), onupdate=func.now()
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR "
            "(account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_snapshot_one_owner",
        ),
        # Partial unique indexes are added in Alembic migration
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # optional / defaulted fields after
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), default=None, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("account_groups.id"), default=None, index=True
    )
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)
    twd_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), default=None)


class AllocationRule(Base):
    __tablename__ = "allocation_rules"
    __table_args__ = (
        CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR "
            "(account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_rule_one_owner",
        ),
        # Partial unique indexes are added in Alembic migration
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    target_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    # optional / defaulted fields after
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trade_accounts.id"), default=None, index=True
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("account_groups.id"), default=None, index=True
    )
    lower_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.03"))
    upper_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.03"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FXRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("date", "from_currency", "to_currency"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    from_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    # optional / defaulted fields after
    to_currency: Mapped[str] = mapped_column(String(10), default="TWD", nullable=False)
