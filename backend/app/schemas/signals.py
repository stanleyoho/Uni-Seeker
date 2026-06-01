"""Pydantic schemas for the pre-market signal board."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RecentSignalRow(BaseModel):
    """One entry in the recent-signals list."""

    symbol: str
    name: str
    # Surface name as shown on the home tile, e.g. ``"golden_cross"``,
    # ``"rsi_oversold_bounce"``, ``"volume_breakout"``, ``"low_base_bounce"``.
    # See ``_normalize_signal_type`` in app/api/v1/signals.py for the
    # registry-key → tile-name mapping.
    signal_type: str
    fired_at: datetime
    current_price: str | None = None
    change_percent: str | None = None


class RecentSignalsResponse(BaseModel):
    signals: list[RecentSignalRow]
    # Breakdown by signal_type → count, used by the 3 mini-tiles
    # ("黃金交叉 8 檔" / "量價突破 12 檔" / "RSI 反彈 5 檔").
    grouped: dict[str, int]
