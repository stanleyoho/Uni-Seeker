"""Pydantic schemas for /api/v1/watchlist endpoints — WATCH-001 / Plan 4 T7."""
from __future__ import annotations

from pydantic import BaseModel, Field


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    created_at: str
