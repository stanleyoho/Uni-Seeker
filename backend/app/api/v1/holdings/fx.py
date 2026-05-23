"""FX rate endpoint — /api/v1/holdings/fx/rate.

Phase 4+ FX support. Spec §11.

Endpoint behaviour:
  - Any authenticated user can hit this; no tier gate (rates are a
    public-utility lookup and we don't want to gate them per tier).
  - `as_of` is optional — omit for spot, supply ISO date for historical.
  - 400 when base/quote are unsupported.
  - 503 when no rate could be obtained (cache miss + fetcher failure).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_serializer

from app.api.v1.holdings._deps import get_fx_service
from app.auth import require_auth
from app.services.portfolio.fx_service import FxRateUnavailable, FxService

router = APIRouter(prefix="/fx", tags=["holdings.fx"])


_SUPPORTED = frozenset({"TWD", "USD", "JPY", "HKD", "EUR", "GBP", "CNY"})


class FxRateResponse(BaseModel):
    base: str
    quote: str
    rate: Decimal
    as_of: date | None

    @field_serializer("rate", when_used="json")
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)


@router.get("/rate", response_model=FxRateResponse)
async def get_fx_rate(
    fx: Annotated[FxService, Depends(get_fx_service)],
    _user: Annotated[object, Depends(require_auth)],
    base: Annotated[
        str,
        Query(min_length=3, max_length=10, description="ISO 4217 base currency"),
    ],
    quote: Annotated[
        str,
        Query(min_length=3, max_length=10, description="ISO 4217 quote currency"),
    ],
    as_of: Annotated[
        date | None,
        Query(description="Optional historical date; omit for spot"),
    ] = None,
) -> FxRateResponse:
    """Return rate such that `quote_amount = base_amount * rate`."""
    base_u = base.upper()
    quote_u = quote.upper()
    if base_u not in _SUPPORTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported_currency:{base_u}",
        )
    if quote_u not in _SUPPORTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported_currency:{quote_u}",
        )

    try:
        rate = await fx.get_rate(base_u, quote_u, as_of=as_of)
    except FxRateUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"fx_rate_unavailable:{base_u}_{quote_u}",
        ) from exc

    return FxRateResponse(base=base_u, quote=quote_u, rate=rate, as_of=as_of)
