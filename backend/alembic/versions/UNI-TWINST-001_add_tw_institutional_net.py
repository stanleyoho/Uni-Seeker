"""Add tw_institutional_net table — TW 三大法人 daily net flow.

Revision ID: UNI_TWINST_001
Revises: UNI_SYNC_002
Create Date: 2026-06-01

Why distinct from f13_*: f13_holdings is the US quarterly 13F dataset
(45-day stale, zero value for day-traders). Taiwan's 三大法人
(外資 / 投信 / 自營) is published daily at ~17:00 Taipei by TWSE and
is the primary chip-data signal a Taiwan day-trader reads each morning.

Schema decisions:
  - BigInteger for *_net — single-day foreign net on TSMC can hit ±10億.
  - Two indexes: (date) for "top-net leaderboard by date" hot path,
    (stock_id, date) for "this stock's last N days" drill-down.
  - UNIQUE (stock_id, date) so the sync task's UPSERT is idempotent.
  - ON DELETE CASCADE on stock_id — matches the rest of the codebase.

This migration is fully reversible.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_TWINST_001"
down_revision: str | None = "UNI_SYNC_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tw_institutional_net",
        sa.Column(
            "id", sa.Integer(), autoincrement=True, primary_key=True,
        ),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "foreign_net", sa.BigInteger(),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "trust_net", sa.BigInteger(),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "dealer_net", sa.BigInteger(),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "total_net", sa.BigInteger(),
            nullable=False, server_default="0",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "stock_id", "date",
            name="uq_tw_institutional_net_stock_date",
        ),
    )
    op.create_index(
        "ix_tw_institutional_net_date",
        "tw_institutional_net",
        ["date"],
    )
    op.create_index(
        "ix_tw_institutional_net_stock_id_date",
        "tw_institutional_net",
        ["stock_id", "date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tw_institutional_net_stock_id_date",
        table_name="tw_institutional_net",
    )
    op.drop_index(
        "ix_tw_institutional_net_date",
        table_name="tw_institutional_net",
    )
    op.drop_table("tw_institutional_net")
