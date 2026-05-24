from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FinancialStatement(Base):
    """Stores quarterly/annual financial statement data from FinMind."""

    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "period",
            "statement_type",
            name="uq_fin_stmt_stock_period_type",
        ),
        Index("ix_fin_stmt_stock_period", "stock_id", "period"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    period: Mapped[str] = mapped_column(String(10))  # "2024-Q1", "2024-Q2", etc.
    statement_type: Mapped[str] = mapped_column(
        String(20),
    )  # "income", "balance", "cashflow"
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    fiscal_quarter: Mapped[int] = mapped_column(SmallInteger)  # 1-4
    data: Mapped[dict] = mapped_column(JSONB, default_factory=dict)
    is_cumulative: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
