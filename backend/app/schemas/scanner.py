"""Pydantic schemas for the signal scanner API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas._base import StrictModel


class SignalScanRequest(StrictModel):
    symbols: list[str] | None = Field(
        default=None,
        description="Stock symbols to scan.  None means scan all.",
    )
    strategy_keys: list[str] | None = Field(
        default=None,
        description="Strategy keys to evaluate.  None means use all strategies.",
    )
    limit: int = Field(default=50, ge=1, le=200)


class SignalDetail(BaseModel):
    strategy: str
    action: str
    strength: float
    reason: str


class StockSignalResponse(BaseModel):
    symbol: str
    name: str
    composite_action: str
    score: float
    signals: list[SignalDetail]


class ScanResponse(BaseModel):
    results: list[StockSignalResponse]
    scan_date: str
    total_scanned: int
    strategies_used: list[str]
