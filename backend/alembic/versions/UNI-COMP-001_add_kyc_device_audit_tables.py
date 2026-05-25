"""Add KYC fields to users, user_devices table, and audit_logs skeleton.

Revision ID: UNI_COMP_001
Revises: UNI_BILL_002
Create Date: 2026-05-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "UNI_COMP_001"
down_revision: str | None = "UNI_BILL_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.add_column("users", sa.Column("risk_tolerance", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("kyc_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_version", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.BigInteger,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "fingerprint_hash", name="uq_user_device"),
    )
    op.create_index("idx_user_devices_user_id", "user_devices", ["user_id"])
    op.create_index("idx_user_devices_fingerprint", "user_devices", ["fingerprint_hash"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="user"),
        sa.Column("user_id", sa.BigInteger,
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("before_state", postgresql.JSONB, nullable=True),
        sa.Column("after_state", postgresql.JSONB, nullable=True),
        sa.Column("event_metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("idx_audit_logs_user_action", "audit_logs", ["user_id", "action"])
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("idx_audit_logs_user_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("idx_user_devices_fingerprint", table_name="user_devices")
    op.drop_index("idx_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_accepted_version")
    op.drop_column("users", "kyc_completed_at")
    op.drop_column("users", "risk_tolerance")
