"""Add processed_webhook_events table for Stripe webhook idempotency.

Revision ID: UNI-BILL-002
Revises: UNI-BILL-001
Create Date: 2026-05-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "UNI-BILL-002"
down_revision: Union[str, None] = "UNI-BILL-001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
