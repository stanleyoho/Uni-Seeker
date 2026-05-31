"""Pydantic schemas for the signal scanner API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SignalScanRequest(BaseModel):
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
    # Names of TA-Lib candlestick patterns firing on the latest bar for
    # this stock (e.g. ``["CDLHAMMER", "CDLENGULFING"]``). Empty list
    # when no patterns fired. Populated by
    # ``app.modules.scanner.patterns.detect_patterns``. The default is
    # preserved so callers that construct this model without OHLC
    # context (notably the per-stock signal endpoint) still work.
    candlestick_patterns: list[str] = Field(default_factory=list)


class ScanResponse(BaseModel):
    results: list[StockSignalResponse]
    scan_date: str
    total_scanned: int
    strategies_used: list[str]
