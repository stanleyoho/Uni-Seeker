"""Add telegram_chat_id to users (13F TG notifications).

Revision ID: UNI_F13_002
Revises: UNI_F13_001
Create Date: 2026-05-19

Adds a nullable per-user Telegram chat identifier so the 13F new-filing
notification service can fan out alerts to subscribers.

Why a per-user column instead of a separate ``user_notification_targets``
table? Phase-1 only supports a single channel (Telegram, send-only) and
the column is small + nullable. A dedicated table can come later when
Email / LINE / Webhook channels (already advertised by
``/notifications/channels``) actually ship.

Telegram chat IDs are signed 64-bit integers (negative for groups), but
we store as VARCHAR(64) to remain forward-compatible with usernames
(``@user`` form) the bot API accepts equally well.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "UNI_F13_002"
down_revision: Union[str, None] = "UNI_F13_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_chat_id")
