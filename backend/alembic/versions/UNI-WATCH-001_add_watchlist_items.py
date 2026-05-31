"""Add watchlist_items table.

Revision ID: UNI_WATCH_001
Revises: UNI_COMP_001
Create Date: 2026-05-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_WATCH_001"
down_revision: str | None = "UNI_COMP_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stock_id",
            sa.BigInteger,
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "stock_id", name="uq_watchlist_user_stock"),
    )
    op.create_index("idx_watchlist_user", "watchlist_items", ["user_id"])
    op.create_index("idx_watchlist_stock", "watchlist_items", ["stock_id"])


def downgrade() -> None:
    op.drop_index("idx_watchlist_stock", table_name="watchlist_items")
    op.drop_index("idx_watchlist_user", table_name="watchlist_items")
    op.drop_table("watchlist_items")
