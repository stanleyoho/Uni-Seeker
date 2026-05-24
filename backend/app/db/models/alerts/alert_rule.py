"""AlertRule ORM — user-defined alert rules (UNI-ALERT-001).

One row per (user, rule). The rule is a declarative condition on either
a single position (POSITION_*) or the user's whole portfolio
(PORTFOLIO_*). Evaluation lives in
``app.modules.alerts.evaluator`` — this model is data-only.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Mirror the migration CHECK strings so the ORM-side validation stays
# in lockstep with the DB. Keep them as plain tuples — the service /
# repo layers import them for input validation.
ALERT_RULE_TYPES = (
    "POSITION_PRICE_DROP",
    "POSITION_PRICE_RISE",
    "PORTFOLIO_VALUE_ABOVE",
    "PORTFOLIO_VALUE_BELOW",
    "POSITION_PNL_PCT_ABOVE",
    "POSITION_PNL_PCT_BELOW",
)
ALERT_STATUSES = ("ACTIVE", "PAUSED", "TRIGGERED")
ALERT_THRESHOLD_TYPES = ("PCT", "ABSOLUTE")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ("
            + ", ".join(f"'{rt}'" for rt in ALERT_RULE_TYPES)
            + ")",
            name="ck_alert_rules_rule_type",
        ),
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{s}'" for s in ALERT_STATUSES)
            + ")",
            name="ck_alert_rules_status",
        ),
        CheckConstraint(
            "threshold_type IN ("
            + ", ".join(f"'{t}'" for t in ALERT_THRESHOLD_TYPES)
            + ")",
            name="ck_alert_rules_threshold_type",
        ),
        Index("ix_alert_rules_user_status", "user_id", "status"),
    )

    # non-default fields first (MappedAsDataclass)
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False
    )
    threshold_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # nullable / defaulted fields
    symbol: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    market: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ACTIVE"
    )
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<AlertRule id={self.id} user_id={self.user_id} "
            f"type={self.rule_type} status={self.status}>"
        )


__all__ = [
    "ALERT_RULE_TYPES",
    "ALERT_STATUSES",
    "ALERT_THRESHOLD_TYPES",
    "AlertRule",
]
