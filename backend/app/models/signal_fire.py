"""Lightweight per-signal-firing event log.

Each row = one strategy fired a BUY (or SELL) on one symbol at one
moment in time. Used by the pre-market signal board on the home page
to render "黃金交叉 8 檔 / 量價突破 12 檔 / RSI 反彈 5 檔" tiles when
the user opens the app in the morning.

Why not reuse ``SignalScanRecord``?
  - That table stores the *aggregate* JSON blob of a single scan run
    (composite_action + per-strategy details). A "fired" tile needs
    one row per (symbol, signal_type, fired_at) so we can:
      - filter by lookback_hours cheaply,
      - group_by signal_type for the badge counts,
      - de-duplicate per symbol so repeated scanner runs don't
        triple-count the same fire.
  - Adding a tiny purpose-built table is cheaper than torturing JSON
    queries across SQLite (test) + Postgres (prod). The two coexist:
    SignalScanRecord remains the "snapshot of scan output", SignalFire
    is the "stream of BUY/SELL events for the dashboard".

The scanner writes here on every scan_many; persistence is best-effort
(scanner does not 500 if SignalFire write fails — that's a chip on top,
not in the critical scan path).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SignalFire(Base):
    """A single strategy-fired event for one symbol at one timestamp."""

    __tablename__ = "signal_fires"
    __table_args__ = (
        # Hot path: "recent fires across all symbols" → filter by
        # fired_at >= now - N hours. fired_at DESC index satisfies
        # both the WHERE and the ORDER BY in one shot.
        Index("ix_signal_fires_fired_at", "fired_at"),
        # Secondary: per-signal-type breakdown counters — small enough
        # to filesort but the index also helps the grouped count path.
        Index("ix_signal_fires_signal_type_fired_at", "signal_type", "fired_at"),
    )

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    # Strategy registry key (e.g. ``"ma_crossover"`` →
    # surface as "golden_cross" for the home tile). The mapping lives in
    # the API layer so the storage stays raw + replayable.
    signal_type: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(10))  # BUY / SELL / HOLD
    strength: Mapped[float] = mapped_column(Numeric(6, 4), default=0.0)
    # Snapshot of the current price at fire time — saved here so the
    # home tile doesn't need a second JOIN against StockPrice for the
    # mini-board render. Source: latest StockPrice.close at scan time.
    fire_price: Mapped[float | None] = mapped_column(
        Numeric(12, 4),
        default=None,
    )
    # ``init=False`` is mandatory under MappedAsDataclass when a server
    # default is the source of truth — otherwise dataclass.__init__
    # demands a ``fired_at`` arg at construction time and explodes the
    # call sites that just want "now" semantics.
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        init=False,
        server_default=func.now(),
    )
