from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SyncState(Base):
    """Tracks the synchronisation progress for each dataset / stock pair."""

    __tablename__ = "sync_states"
    __table_args__ = (
        UniqueConstraint("dataset", "stock_id", name="uq_sync_state"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(50))
    stock_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
        default=None,
    )
    last_synced_date: Mapped[date | None] = mapped_column(Date, default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="idle")
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
