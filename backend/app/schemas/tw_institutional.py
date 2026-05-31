"""Pydantic schemas for the TW 三大法人 surface."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class TwInstitutionalTopRow(BaseModel):
    """One leaderboard row in the top-net response."""

    symbol: str
    name: str
    # Net amount for the requested *kind* (foreign / trust / dealer / total).
    # Positive = net buy (institutional accumulation),
    # negative = net sell (institutional distribution).
    net_amount: int
    # Latest available close price for the same trading date as the net.
    # `None` when StockPrice has no row for that date (silent fallback —
    # we'd rather render "—" than 500 the leaderboard).
    price: str | None = None
    change_percent: str | None = None


class TwInstitutionalTopNetResponse(BaseModel):
    """Leaderboard response for /tw-institutional/top-net."""

    data: list[TwInstitutionalTopRow]
    date: str
    kind: str  # foreign | trust | dealer | total
    direction: str  # buy | sell
    message: str | None = Field(
        default=None,
        description="Set to a hint when ``data`` is empty (e.g. no DB rows).",
    )


class TwInstitutionalDayRecord(BaseModel):
    """One day's three-way net for a single symbol (drill-down view)."""

    date: date
    foreign_net: int
    trust_net: int
    dealer_net: int
    total_net: int


class TwInstitutionalSymbolResponse(BaseModel):
    """Per-symbol history response for /tw-institutional/symbol/{symbol}."""

    symbol: str
    name: str
    data: list[TwInstitutionalDayRecord]
