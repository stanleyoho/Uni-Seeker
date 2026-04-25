from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import Market, MarketType


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    market: Mapped[Market] = mapped_column(MarketType)
    industry_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("industries.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
