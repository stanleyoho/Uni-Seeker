"""Add Portfolio Tracker Phase 1 tables.

Revision ID: UNI_PORT_001
Revises: UNI_WATCH_001
Create Date: 2026-05-20

Creates the four Phase 1 tables for the Portfolio Tracker module
(design doc §6.2 Tables 1-4):
  - portfolio_accounts
  - portfolio_trades
  - portfolio_lots
  - portfolio_positions

Phase 3 (portfolio_dividends) and Phase 4+ (holdings_snapshots) are
intentionally deferred — they will get their own migrations.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "UNI_PORT_001"
down_revision: Union[str, None] = "UNI_WATCH_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `market_enum` already exists in the DB (created by the 3NF schema
# migration for stocks). Reuse the named PG ENUM with create_type=False
# so upgrade does not try to CREATE TYPE a second time, and downgrade
# does not DROP it (other tables still depend on it).
def _market_enum() -> PgEnum:
    return PgEnum(
        "TW_TWSE", "TW_TPEX", "US_NYSE", "US_NASDAQ",
        name="market_enum", create_type=False,
    )


def upgrade() -> None:
    # ── portfolio_accounts ────────────────────────────────────────────────
    op.create_table(
        "portfolio_accounts",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("market", _market_enum(), nullable=False),
        sa.Column(
            "currency", sa.String(length=10),
            nullable=False, server_default="TWD",
        ),
        sa.Column("broker", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_portfolio_accounts_user_id", "portfolio_accounts", ["user_id"],
    )

    # ── portfolio_trades ──────────────────────────────────────────────────
    op.create_table(
        "portfolio_trades",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "account_id", sa.BigInteger,
            sa.ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", _market_enum(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "fee", sa.Numeric(precision=24, scale=8),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "tax", sa.Numeric(precision=24, scale=8),
            nullable=False, server_default="0",
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(price IS NULL) OR (price > 0)",
            name="ck_portfolio_trades_price_positive",
        ),
        sa.CheckConstraint(
            "(quantity IS NULL) OR (quantity > 0)",
            name="ck_portfolio_trades_qty_positive",
        ),
    )
    op.create_index(
        "ix_portfolio_trades_account_symbol",
        "portfolio_trades",
        ["account_id", "symbol", "market", "trade_date"],
    )

    # ── portfolio_lots ────────────────────────────────────────────────────
    op.create_table(
        "portfolio_lots",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "trade_id", sa.BigInteger,
            sa.ForeignKey("portfolio_trades.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id", sa.BigInteger,
            sa.ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", _market_enum(), nullable=False),
        sa.Column("original_qty", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column(
            "is_exhausted", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.CheckConstraint(
            "original_qty > 0",
            name="ck_portfolio_lots_original_qty_positive",
        ),
        sa.CheckConstraint(
            "remaining_qty >= 0",
            name="ck_portfolio_lots_remaining_qty_nonneg",
        ),
        sa.CheckConstraint(
            "cost_per_unit > 0",
            name="ck_portfolio_lots_cost_positive",
        ),
    )
    op.create_index(
        "ix_portfolio_lots_fifo",
        "portfolio_lots",
        ["account_id", "symbol", "market", "is_exhausted", "trade_id"],
    )
    op.create_index(
        "ix_portfolio_lots_is_exhausted",
        "portfolio_lots",
        ["is_exhausted"],
    )

    # ── portfolio_positions ───────────────────────────────────────────────
    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "account_id", sa.BigInteger,
            sa.ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", _market_enum(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column(
            "quantity", sa.Numeric(precision=24, scale=8),
            nullable=False, server_default="0",
        ),
        sa.Column("avg_cost_fifo", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column(
            "realized_pnl", sa.Numeric(precision=24, scale=8),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "is_closed", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "last_updated", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "account_id", "symbol", "market",
            name="uq_portfolio_positions_account_symbol_market",
        ),
        sa.CheckConstraint(
            "quantity >= 0",
            name="ck_portfolio_positions_qty_nonneg",
        ),
    )
    op.create_index(
        "ix_portfolio_positions_account_id",
        "portfolio_positions",
        ["account_id"],
    )
    op.create_index(
        "ix_portfolio_positions_is_closed",
        "portfolio_positions",
        ["is_closed"],
    )


def downgrade() -> None:
    # Drop in reverse-FK order: positions / lots → trades → accounts.
    op.drop_index("ix_portfolio_positions_is_closed", table_name="portfolio_positions")
    op.drop_index("ix_portfolio_positions_account_id", table_name="portfolio_positions")
    op.drop_table("portfolio_positions")

    op.drop_index("ix_portfolio_lots_is_exhausted", table_name="portfolio_lots")
    op.drop_index("ix_portfolio_lots_fifo", table_name="portfolio_lots")
    op.drop_table("portfolio_lots")

    op.drop_index("ix_portfolio_trades_account_symbol", table_name="portfolio_trades")
    op.drop_table("portfolio_trades")

    op.drop_index("ix_portfolio_accounts_user_id", table_name="portfolio_accounts")
    op.drop_table("portfolio_accounts")
