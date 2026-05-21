"""Filing + holdings + diff endpoints — /api/v1/institutional/filers/{id}.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§5.3 + §5.4 (diff). Access control: every read is gated on subscription
status by the service (raises `F13FilerNotFound` when not subscribed).
"""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.institutional import _detail as detail
from app.api.v1.institutional._deps import get_edgar_client
from app.auth import require_auth
from app.modules.institutional.edgar_client import EdgarClient
from app.schemas.institutional.filing import (
    F13DiffResponse,
    F13FilingResponse,
    F13HoldingChangeResponse,
    F13HoldingResponse,
    F13HoldingsAtPeriodResponse,
)
from app.services.institutional import (
    F13FilerNotFound,
    F13FilingNotFound,
    F13FilingService,
)

router = APIRouter(
    prefix="/filers/{filer_id}", tags=["institutional.filings"]
)

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
EdgarDep = Annotated[EdgarClient, Depends(get_edgar_client)]


@router.get(
    "/filings",
    response_model=list[F13FilingResponse],
)
async def list_filings(
    filer_id: int,
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[F13FilingResponse]:
    """Paginated list of `f13_filings` for the subscribed filer.

    Ordered by `report_period_end DESC` (most recent first). 404 when
    the user is not subscribed to this filer.
    """
    svc = F13FilingService(db, user, edgar)  # type: ignore[arg-type]
    try:
        filings = await svc.list_filings_for_filer(
            filer_id, limit=limit, offset=offset
        )
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    return [F13FilingResponse.model_validate(f) for f in filings]


@router.get(
    "/holdings",
    response_model=F13HoldingsAtPeriodResponse,
)
async def get_holdings(
    filer_id: int,
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
    period: str = Query(
        "latest",
        description="'latest' or ISO date string '2025-12-31'",
    ),
) -> F13HoldingsAtPeriodResponse:
    """Filing + holdings rows for one period."""
    svc = F13FilingService(db, user, edgar)  # type: ignore[arg-type]
    try:
        filing, holdings = await svc.get_holdings_at_period(
            filer_id=filer_id, period=period
        )
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    except F13FilingNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILING_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail.F13_INVALID_INPUT,
        ) from exc
    return F13HoldingsAtPeriodResponse(
        filing=F13FilingResponse.model_validate(filing),
        holdings=[F13HoldingResponse.model_validate(h) for h in holdings],
    )


@router.get(
    "/diff",
    response_model=F13DiffResponse,
)
async def get_diff(
    filer_id: int,
    db: DbDep,
    user: UserDep,
    edgar: EdgarDep,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
) -> F13DiffResponse:
    """QoQ diff between two stored filings.

    Both `from` and `to` MUST already exist in `f13_filings`; the
    endpoint does not refresh implicitly (Q1 = on-demand only). Use
    `POST /filers/{id}/refresh` first if needed.
    """
    svc = F13FilingService(db, user, edgar)  # type: ignore[arg-type]
    try:
        _, _, changes = await svc.compute_diff(
            filer_id=filer_id, from_date=from_date, to_date=to_date
        )
    except F13FilerNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILER_NOT_FOUND,
        ) from exc
    except F13FilingNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.F13_FILING_NOT_FOUND,
        ) from exc
    return F13DiffResponse(
        prev_period=from_date,
        curr_period=to_date,
        changes=[
            F13HoldingChangeResponse(
                cusip=c.cusip,
                name_of_issuer=c.name_of_issuer,
                change_type=c.change_type.value,
                prev_shares=c.prev_shares,
                curr_shares=c.curr_shares,
                delta_shares=c.delta_shares,
                delta_pct=c.delta_pct,
                prev_value_usd=c.prev_value_usd,
                curr_value_usd=c.curr_value_usd,
                delta_value_usd=c.delta_value_usd,
            )
            for c in changes
        ],
    )
