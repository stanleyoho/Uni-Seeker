"""Alpha158-style factor endpoints (A2 audit item).

Exposes the bounded factor set from :mod:`app.modules.factors`:

* ``GET  /factors``                 — catalog (name + formula) of all factors
* ``POST /factors/compute``         — factor vector for one symbol
* ``POST /factors/compute/batch``   — factor vectors for several symbols

The HTTP layer is thin: it resolves symbols to ``Stock`` rows and delegates
all math to the pure factor functions via the factor service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_stock_or_404
from app.schemas.factor import (
    FactorBatchRequest,
    FactorBatchResponse,
    FactorCatalogEntry,
    FactorCatalogResponse,
    FactorVectorRequest,
    FactorVectorResponse,
)
from app.services.factors import compute_symbol_factors
from app.services.factors.service import factor_catalog

router = APIRouter(prefix="/factors", tags=["factors"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Cap batch size to bound DB work (one history query per symbol, plus a
# benchmark query). A typo'd 10k-symbol request should 422, not hammer the DB.
_MAX_BATCH = 50


@router.get("/", response_model=FactorCatalogResponse)
def list_factors() -> FactorCatalogResponse:
    """List every available factor with its formula (living documentation)."""
    return FactorCatalogResponse(
        factors=[FactorCatalogEntry(name=n, formula=f) for n, f in factor_catalog()]
    )


@router.post("/compute", response_model=FactorVectorResponse)
async def compute_factors(
    req: FactorVectorRequest,
    db: DbSession,
) -> FactorVectorResponse:
    """Compute the Alpha158-style factor vector for one symbol."""
    stock = await get_stock_or_404(db, req.symbol)
    result = await compute_symbol_factors(db, stock)
    return FactorVectorResponse(
        symbol=result.symbol,
        bar_count=result.bar_count,
        factors=result.factors,
        composite_momentum=result.composite_momentum,
    )


@router.post("/compute/batch", response_model=FactorBatchResponse)
async def compute_factors_batch(
    req: FactorBatchRequest,
    db: DbSession,
) -> FactorBatchResponse:
    """Compute factor vectors for a batch of symbols.

    Unknown symbols 404 the whole request (fail loud) — the same contract as
    the single-symbol endpoint, applied per symbol.
    """
    if not req.symbols:
        raise HTTPException(status_code=422, detail="symbols must not be empty")
    if len(req.symbols) > _MAX_BATCH:
        raise HTTPException(
            status_code=422,
            detail=f"batch size {len(req.symbols)} exceeds max {_MAX_BATCH}",
        )

    results: list[FactorVectorResponse] = []
    for symbol in req.symbols:
        stock = await get_stock_or_404(db, symbol)
        result = await compute_symbol_factors(db, stock)
        results.append(
            FactorVectorResponse(
                symbol=result.symbol,
                bar_count=result.bar_count,
                factors=result.factors,
                composite_momentum=result.composite_momentum,
            )
        )
    return FactorBatchResponse(results=results)
