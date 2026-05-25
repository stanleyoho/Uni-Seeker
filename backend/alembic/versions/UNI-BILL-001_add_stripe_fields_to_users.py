"""Add Stripe fields to users table.

Revision ID: UNI_BILL_001
Revises: e900cd627d8a
Create Date: 2026-05-11

Note: revision identifier uses underscores; alembic 1.18+ rejects hyphen.
Filename keeps hyphens for human readability of the BILL series.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_BILL_001"
down_revision: str | None = "e900cd627d8a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
