from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import NotificationStatus, NotificationStatusType


class NotificationRule(Base):
    __tablename__ = "notification_rules"
    __table_args__ = (
        Index("ix_notification_rules_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(50))  # price_alert, indicator_alert, schedule
    symbol: Mapped[str] = mapped_column(String(20), default="")
    conditions: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    condition_logic: Mapped[str] = mapped_column(String(10), default="AND")
    channels: Mapped[str] = mapped_column(String(200), default='["telegram"]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_user_id", "user_id"),
        Index("ix_notification_logs_rule_id", "rule_id"),
        Index("ix_notification_logs_status", "status"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    channel: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("notification_rules.id", ondelete="SET NULL"),
        default=None,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        NotificationStatusType,
        default=NotificationStatus.PENDING,
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
