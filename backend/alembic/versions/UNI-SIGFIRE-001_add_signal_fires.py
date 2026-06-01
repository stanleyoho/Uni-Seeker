"""Add signal_fires table — pre-market signal board event log.

Revision ID: UNI_SIGFIRE_001
Revises: UNI_TWINST_001
Create Date: 2026-06-01

One row per (symbol, signal_type, fired_at). Powers the home page
"昨日 / 盤前訊號" mini-board that day-traders glance at first thing
in the morning.

Index strategy:
  - ix_signal_fires_fired_at — supports "recent fires" lookback_hours
    range scan + ORDER BY DESC in one shot.
  - ix_signal_fires_signal_type_fired_at — helps the grouped-count
    breakdown ("golden_cross: 8") avoid a full filesort when the table
    grows past a few thousand rows.

Why not reuse signal_scans: that table is the JSON aggregate snapshot
per scan run, not a per-fire event stream. See model docstring.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_SIGFIRE_001"
down_revision: str | None = "UNI_TWINST_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_fires",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            primary_key=True,
        ),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column(
            "strength",
            sa.Numeric(precision=6, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "fire_price",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
        ),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_signal_fires_fired_at",
        "signal_fires",
        ["fired_at"],
    )
    op.create_index(
        "ix_signal_fires_signal_type_fired_at",
        "signal_fires",
        ["signal_type", "fired_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_fires_signal_type_fired_at",
        table_name="signal_fires",
    )
    op.drop_index("ix_signal_fires_fired_at", table_name="signal_fires")
    op.drop_table("signal_fires")
