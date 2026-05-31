"""TW 三大法人 (Foreign / Trust / Dealer) per-day net flow.

Source: FinMind dataset ``TaiwanStockInstitutionalInvestorsBuySell``
(published ~17:00 Taipei after market close). Distinct from the
``13F`` (US quarterly) institutional surface — Taiwan day-traders
read these numbers the morning after to plan their entries.

Net amount semantics (BigInt, raw shares):
    foreign_net = Foreign_Investor (FINI + FIDI)  buy − sell
    trust_net   = Investment_Trust                buy − sell
    dealer_net  = Dealer_self + Dealer_Hedging    buy − sell
    total_net   = foreign_net + trust_net + dealer_net

Units are *shares* (not 仟股 / not lots) to match the raw FinMind
payload. The frontend should convert to 億 / 萬 for display.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TwInstitutionalNet(Base):
    """Per-(stock, date) net buy/sell across the three institutional kinds."""

    __tablename__ = "tw_institutional_net"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "date",
            name="uq_tw_institutional_net_stock_date",
        ),
        # Hot path 1: "top net foreign on date X" → index on (date).
        # Hot path 2: "this stock's last N days" → (stock_id, date).
        # Both indexes are needed: the leaderboard query filters on date
        # and orders by foreign_net/trust_net/dealer_net (varies), so a
        # 3-column composite per kind would be overkill for ~2k tickers
        # — PG just filesorts on the small daily slice.
        Index("ix_tw_institutional_net_date", "date"),
        Index(
            "ix_tw_institutional_net_stock_id_date",
            "stock_id",
            "date",
        ),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)

    foreign_net: Mapped[int] = mapped_column(BigInteger, default=0)
    trust_net: Mapped[int] = mapped_column(BigInteger, default=0)
    dealer_net: Mapped[int] = mapped_column(BigInteger, default=0)
    total_net: Mapped[int] = mapped_column(BigInteger, default=0)

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
