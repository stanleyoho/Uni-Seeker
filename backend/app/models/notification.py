from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rule_type: Mapped[str] = mapped_column(String(50))  # price_alert, indicator_alert, schedule
    symbol: Mapped[str] = mapped_column(String(20), default="")
    conditions: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    condition_logic: Mapped[str] = mapped_column(String(10), default="AND")
    channels: Mapped[str] = mapped_column(String(200), default='["telegram"]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    channel: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    rule_id: Mapped[int | None] = mapped_column(default=None)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )
