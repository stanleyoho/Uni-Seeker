from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PriceEstimate(Base):
    __tablename__ = "price_estimates"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "date", "model_type", name="uq_price_estimates_stock_date_model"
        ),
        Index("ix_price_estimates_stock_date", "stock_id", "date"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)
    
    # Model type: 'dcf', 'ddm', 'pe_band', 'pb_band', 'composite'
    model_type: Mapped[str] = mapped_column(String(30))
    
    cheap_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), default=None)
    fair_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), default=None)
    expensive_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), default=None)
    
    # Confidence score: 0.0 to 1.0
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.5)
    
    # Model-specific parameters and metadata
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default='{}', default_factory=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
