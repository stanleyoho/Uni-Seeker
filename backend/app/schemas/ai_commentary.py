"""Pydantic schemas for the AI commentary endpoint."""

from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, Field


class CommentarySourceSchema(BaseModel):
    """A single factual source surfaced for transparency."""

    kind: str = Field(description="Source kind, e.g. price/rsi/macd/bb/sector/patterns")
    detail: str = Field(description="Human-readable summary of the underlying number")


class AiCommentaryResponse(BaseModel):
    """Daily AI commentary for a single stock.

    `confidence` is the share of signals that contributed to the
    narrative (weighted). Below ~0.5 callers should surface a
    "data sparse" UI hint.
    """

    symbol: str
    date: date_type
    commentary: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[CommentarySourceSchema] = Field(default_factory=list)
