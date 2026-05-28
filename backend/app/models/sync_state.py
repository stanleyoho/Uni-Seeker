from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SyncState(Base):
    """Tracks the synchronisation progress for each dataset / stock pair."""

    __tablename__ = "sync_states"
    __table_args__ = (
        # Partial unique indexes — the per-stock variant uniquely identifies
        # `(dataset, stock_id)` rows; the global variant ensures at most one
        # `(dataset, NULL)` row used for the orchestrator's scheduler state.
        # Declared here (rather than as a UniqueConstraint) because PG has
        # no partial UNIQUE constraint — only a partial UNIQUE INDEX is
        # supported. The `*_where` kwargs ensure both PG and sqlite (3.8+)
        # generate the partial form during Base.metadata.create_all.
        # Discovered 2026-05-27: previously these were marked "created via
        # migration" but no migration actually creates them, so production
        # PG had been missing the indexes for ~27 days — silently breaking
        # the margin / revenue / per_pbr sync tasks every catchup run.
        Index(
            "uq_sync_state_with_stock",
            "dataset",
            "stock_id",
            unique=True,
            postgresql_where=text("stock_id IS NOT NULL"),
            sqlite_where=text("stock_id IS NOT NULL"),
        ),
        Index(
            "uq_sync_state_global",
            "dataset",
            unique=True,
            postgresql_where=text("stock_id IS NULL"),
            sqlite_where=text("stock_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(50))
    stock_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stocks.id", ondelete="CASCADE"),
        default=None,
    )
    last_synced_date: Mapped[date | None] = mapped_column(Date, default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    error_message: Mapped[str | None] = mapped_column(String(2000), default=None)
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
