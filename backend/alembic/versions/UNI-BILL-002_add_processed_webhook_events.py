"""Add processed_webhook_events table for Stripe webhook idempotency.

Revision ID: UNI_BILL_002
Revises: UNI_BILL_001
Create Date: 2026-05-14
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "UNI_BILL_002"
down_revision: str | None = "UNI_BILL_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_webhook_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "provider",
            sa.String(length=20),
            nullable=False,
            server_default="stripe",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("event_type", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("processed_webhook_events")
