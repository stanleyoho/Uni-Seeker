"""Pydantic schemas for the 四大買賣點 (Best Four Buy/Sell Points) API.

The endpoint serves *cached* results computed by the daily scheduled scan
(see ``app.services.best_four_point.scan_service``); the API never computes
the universe live. Response models inherit ``StrictModel`` so any drift
between the backend payload and the frontend's generated types fails loud at
the schema-contract CI gate rather than silently dropping fields.
"""

from __future__ import annotations

from pydantic import Field

from app.schemas._base import StrictModel


class BestFourPointRow(StrictModel):
    """One symbol's 四大買賣點 outcome for the scan date."""

    symbol: str
    name: str
    # 買進 / 賣出 / 觀望
    verdict: str
    # Triggered (bias-gated) buy reasons, e.g. ["量大收紅", "三日均價由下往上"].
    buy_points: list[str] = Field(default_factory=list)
    # Triggered (bias-gated) sell reasons.
    sell_points: list[str] = Field(default_factory=list)
    # #buy − #sell. Positive leans buy, negative leans sell.
    net_score: int = 0
    # Latest close used for the computation, Decimal-as-string per the
    # app-wide numeric convention. None when the price was unavailable.
    last_close: str | None = None


class BestFourPointResponse(StrictModel):
    """Cached daily 四大買賣點 scan result (TW universe)."""

    # ISO date (Asia/Taipei) the cached scan was computed for. None when no
    # scan has run yet (empty DB / fresh deploy) — the frontend renders an
    # empty state in that case.
    scan_date: str | None = None
    # Symbols whose verdict == 買進, sorted by net_score desc.
    buy_signals: list[BestFourPointRow] = Field(default_factory=list)
    # Symbols whose verdict == 賣出, sorted by net_score asc (most-negative first).
    sell_signals: list[BestFourPointRow] = Field(default_factory=list)
    # Total TW symbols evaluated in the cached scan.
    total_scanned: int = 0
