from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SignalScanRecord(Base):
    """Captures signal scan results for a symbol on a given date."""

    __tablename__ = "signal_scans"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    scan_date: Mapped[date] = mapped_column(Date, index=True)
    signals_json: Mapped[dict] = mapped_column(JSON, default_factory=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now(),
    )
