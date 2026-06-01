"""add_journal_tables

Revision ID: af683002958e
Revises: 8bda05408c97
Create Date: 2026-05-04 16:29:02.062267
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "af683002958e"
down_revision: str | None = "8bda05408c97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_currency", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("from_currency", sa.String(length=10), nullable=False),
        sa.Column("rate", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("to_currency", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "from_currency", "to_currency"),
    )
    op.create_table(
        "trade_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("broker", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "account_group_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("target_weight", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["trade_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["account_groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "account_id"),
    )
    op.create_table(
        "allocation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("target_weight", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("lower_threshold", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("upper_threshold", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR (account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_rule_one_owner",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trade_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["account_groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_allocation_rules_account_id"), "allocation_rules", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_allocation_rules_group_id"), "allocation_rules", ["group_id"], unique=False
    )
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("total_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("twd_value", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.CheckConstraint(
            "(account_id IS NOT NULL AND group_id IS NULL) OR (account_id IS NULL AND group_id IS NOT NULL)",
            name="ck_snapshot_one_owner",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trade_accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["account_groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_portfolio_snapshots_account_id"),
        "portfolio_snapshots",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_snapshots_group_id"), "portfolio_snapshots", ["group_id"], unique=False
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("avg_cost_fifo", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["trade_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "symbol", "market"),
    )
    op.create_index(op.f("ix_positions_account_id"), "positions", ["account_id"], unique=False)
    op.create_index(op.f("ix_positions_is_closed"), "positions", ["is_closed"], unique=False)
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("fee", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("tax", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("trade_fx_rate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["trade_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trades_account_symbol",
        "trades",
        ["account_id", "symbol", "market", "date"],
        unique=False,
    )
    op.create_table(
        "trade_lots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("original_qty", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("is_exhausted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["trade_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trade_lots_fifo",
        "trade_lots",
        ["account_id", "symbol", "market", "is_exhausted", "trade_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trade_lots_is_exhausted"), "trade_lots", ["is_exhausted"], unique=False
    )
    # Partial unique indexes (cannot be expressed in SQLAlchemy __table_args__)
    op.execute(
        "CREATE UNIQUE INDEX uq_account_snapshot ON portfolio_snapshots(account_id, date) WHERE account_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_group_snapshot ON portfolio_snapshots(group_id, date) WHERE group_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rule_account_symbol ON allocation_rules(account_id, symbol) WHERE account_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rule_group_symbol ON allocation_rules(group_id, symbol) WHERE group_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_account_snapshot")
    op.execute("DROP INDEX IF EXISTS uq_group_snapshot")
    op.execute("DROP INDEX IF EXISTS uq_rule_account_symbol")
    op.execute("DROP INDEX IF EXISTS uq_rule_group_symbol")
    op.drop_index(op.f("ix_trade_lots_is_exhausted"), table_name="trade_lots")
    op.drop_index("ix_trade_lots_fifo", table_name="trade_lots")
    op.drop_table("trade_lots")
    op.drop_index("ix_trades_account_symbol", table_name="trades")
    op.drop_table("trades")
    op.drop_index(op.f("ix_positions_is_closed"), table_name="positions")
    op.drop_index(op.f("ix_positions_account_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_portfolio_snapshots_group_id"), table_name="portfolio_snapshots")
    op.drop_index(op.f("ix_portfolio_snapshots_account_id"), table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
    op.drop_index(op.f("ix_allocation_rules_group_id"), table_name="allocation_rules")
    op.drop_index(op.f("ix_allocation_rules_account_id"), table_name="allocation_rules")
    op.drop_table("allocation_rules")
    op.drop_table("account_group_members")
    op.drop_table("trade_accounts")
    op.drop_table("fx_rates")
    op.drop_table("account_groups")
