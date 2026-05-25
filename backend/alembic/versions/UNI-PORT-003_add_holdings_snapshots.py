"""Add holdings_snapshots table — Portfolio Tracker Phase 5.

Revision ID: UNI_PORT_003
Revises: UNI_PORT_002
Create Date: 2026-05-19

Spec §6 Table 6 (holdings_snapshots Phase 4+). Daily-snapshot persistence
backing TWR / Sharpe / max-drawdown analytics (Phase 5).

Why a new namespace
-------------------
`app/models/journal.py` already defines `portfolio_snapshots` (trade
journal Plan 4 — currently empty, decision §14 Q14.8 = **keep**). To
avoid the conflict we use `holdings_snapshots` here. The model class is
`HoldingsSnapshot` (so `PortfolioSnapshot` continues to refer to the
trade-journal table unambiguously).

Uniqueness model
----------------
One UNIQUE (user_id, account_id, snapshot_date). `account_id IS NULL`
marks the per-user roll-up; SQL UNIQUE treats NULL as distinct so the
user-wide row coexists with per-account rows on the same date. The
daily snapshot job's UPSERT keeps "one user-wide row per day" true in
practice.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_PORT_003"
down_revision: str | None = "UNI_PORT_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "holdings_snapshots",
        sa.Column(
            "id", sa.BigInteger, sa.Identity(always=True), primary_key=True,
        ),
        sa.Column(
            "user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id", sa.BigInteger,
            sa.ForeignKey("portfolio_accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "total_value", sa.Numeric(precision=24, scale=8), nullable=False,
        ),
        sa.Column(
            "total_cost", sa.Numeric(precision=24, scale=8), nullable=False,
        ),
        sa.Column(
            "total_unrealized_pnl", sa.Numeric(precision=24, scale=8),
            nullable=False,
        ),
        sa.Column(
            "realized_pnl_cum", sa.Numeric(precision=24, scale=8),
            nullable=False,
        ),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "account_id", "snapshot_date",
            name="uq_holdings_snapshots_user_account_date",
        ),
        sa.CheckConstraint(
            "total_value >= 0",
            name="ck_holdings_snapshots_total_value_nonneg",
        ),
        sa.CheckConstraint(
            "position_count >= 0",
            name="ck_holdings_snapshots_position_count_nonneg",
        ),
    )
    op.create_index(
        "ix_holdings_snapshots_user_id",
        "holdings_snapshots",
        ["user_id"],
    )
    op.create_index(
        "ix_holdings_snapshots_account_id",
        "holdings_snapshots",
        ["account_id"],
    )
    op.create_index(
        "ix_holdings_snapshots_snapshot_date",
        "holdings_snapshots",
        ["snapshot_date"],
    )
    # Hot-path composite indices for the latest-N per user / per account
    # queries used by AnalyticsService.
    op.create_index(
        "ix_holdings_snapshots_user_date",
        "holdings_snapshots",
        ["user_id", sa.text("snapshot_date DESC")],
    )
    op.create_index(
        "ix_holdings_snapshots_account_date",
        "holdings_snapshots",
        ["account_id", sa.text("snapshot_date DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_holdings_snapshots_account_date",
        table_name="holdings_snapshots",
    )
    op.drop_index(
        "ix_holdings_snapshots_user_date",
        table_name="holdings_snapshots",
    )
    op.drop_index(
        "ix_holdings_snapshots_snapshot_date",
        table_name="holdings_snapshots",
    )
    op.drop_index(
        "ix_holdings_snapshots_account_id",
        table_name="holdings_snapshots",
    )
    op.drop_index(
        "ix_holdings_snapshots_user_id",
        table_name="holdings_snapshots",
    )
    op.drop_table("holdings_snapshots")
