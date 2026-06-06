"""Schemas for the Alpha158-style factor endpoints.

Request bodies inherit :class:`StrictModel` (reject unknown fields, per the
repo-wide policy in ``app.schemas._base``). Response models are plain
``BaseModel`` so additive backend fields don't force a frontend schema bump.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas._base import StrictModel


class FactorVectorRequest(StrictModel):
    """Request a single symbol's factor vector."""

    symbol: str


class FactorBatchRequest(StrictModel):
    """Request factor vectors for several symbols at once."""

    symbols: list[str]


class FactorVectorResponse(BaseModel):
    """Computed factor vector for one symbol.

    ``factors`` maps factor name -> value, where ``None`` marks a factor
    whose lookback window is unmet (insufficient bars) or whose inputs were
    degenerate. ``bar_count`` lets the client reason about warmup.
    """

    symbol: str
    bar_count: int
    factors: dict[str, float | None]
    composite_momentum: float | None


class FactorBatchResponse(BaseModel):
    """Factor vectors for a batch of symbols."""

    results: list[FactorVectorResponse]


class FactorCatalogEntry(BaseModel):
    """One factor's name and human-readable formula (living documentation)."""

    name: str
    formula: str


class FactorCatalogResponse(BaseModel):
    """The catalog of every available factor and its formula."""

    factors: list[FactorCatalogEntry]
