from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarginTrading(Base):
    __tablename__ = "margin_trading"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_margin_symbol_date"),)

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    margin_buy: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_sell: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    margin_limit: Mapped[int] = mapped_column(BigInteger, default=0)
    short_buy: Mapped[int] = mapped_column(BigInteger, default=0)
    short_sell: Mapped[int] = mapped_column(BigInteger, default=0)
    short_balance: Mapped[int] = mapped_column(BigInteger, default=0)
    short_limit: Mapped[int] = mapped_column(BigInteger, default=0)
    offset: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
