"""CSV export endpoints — /api/v1/holdings/exports/*.csv.

Phase 4 tax-export hook (spec §11 extensibility). Each route returns
``Response`` with ``Content-Type: text/csv; charset=utf-8`` and a
``Content-Disposition: attachment; filename="..."`` header so the
browser triggers a download instead of rendering in-page.

Tier guard
----------
We do NOT use the dependency-layer ``tier_guard(feature='tax_export')``
here. The service raises ``TierFeatureUnavailable`` from inside every
``export_*`` method (service-level second line — spec §9 雙保險). We
catch it here and emit ``403 feature_unavailable:tax_export``. This
matches the dividend endpoint pattern when only the service-level
guard fires; saves us the small bit of duplication of also putting the
declarative guard on every route.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.auth import require_auth
from app.services.portfolio import CsvExportService, TaxReportService
from app.services.portfolio.exceptions import TierFeatureUnavailable

router = APIRouter(prefix="/exports", tags=["holdings.exports"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]


_MEDIA_TYPE = "text/csv; charset=utf-8"


def _today_iso() -> str:
    """ISO date for the export's default filename — matches the
    ``yyyy-MM-dd`` slug Excel autodetects as a date column when the
    file lands in a folder.
    """
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _disposition(prefix: str) -> dict[str, str]:
    """Build the ``Content-Disposition`` header so the browser triggers
    a download with a recognisable filename."""
    return {"Content-Disposition": (f'attachment; filename="{prefix}-{_today_iso()}.csv"')}


def _translate_tier(exc: TierFeatureUnavailable) -> HTTPException:
    """Map the service-layer tier exception → 403 with the canonical
    detail string. Single helper keeps the four endpoints DRY."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=detail.feature_unavailable(exc.feature),
    )


@router.get("/trades.csv")
async def export_trades(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(default=None),
    date_from: date_type | None = Query(default=None),
    date_to: date_type | None = Query(default=None),
) -> Response:
    """Export the user's trades as CSV.

    Tier: ``tax_export`` (PRO only per ``config/tier_limits.yaml``).
    Filters: ``account_id`` / ``date_from`` / ``date_to`` (inclusive).
    """
    service = CsvExportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_trades(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("trades"),
    )


@router.get("/positions.csv")
async def export_positions(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(default=None),
) -> Response:
    """Export every position (open + closed) as CSV.

    Uses the latest ``stock_prices`` close (not yfinance) for
    ``last_price`` so the export is deterministic.
    """
    service = CsvExportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_positions(account_id=account_id)
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("positions"),
    )


@router.get("/dividends.csv")
async def export_dividends(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(default=None),
    date_from: date_type | None = Query(default=None),
    date_to: date_type | None = Query(default=None),
) -> Response:
    """Export every dividend event as CSV.

    Filters apply to ``ex_dividend_date``. Both CASH and STOCK rows are
    included; the service stores STOCK ratios in ``amount_per_share``
    (CHECK > 0) so they appear as a positive numeric column.
    """
    service = CsvExportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_dividends(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("dividends"),
    )


@router.get("/summary.csv")
async def export_summary(
    db: DbDep,
    user: UserDep,
) -> Response:
    """Export a one-row portfolio summary CSV.

    No filters — always user-wide. Mirrors the wire schema of
    ``GET /holdings/summary`` with two extras: ``daily_change`` (mapped
    from ``total_daily_change``) and ``exported_at`` (UTC timestamp).
    """
    service = CsvExportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_summary()
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("summary"),
    )


@router.get("/form8949.csv")
async def export_form_8949(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(default=None),
    tax_year: int | None = Query(default=None),
    apply_wash_sales: bool = Query(
        default=False,
        description=(
            "When true, run IRS §1091 wash-sale detection and populate "
            "Code='W' + Adjustment columns. Default false for backward "
            "compatibility with the Round 10 export shape."
        ),
    ),
) -> Response:
    """Export Form 8949-style matched buy-sell pairs as CSV.

    Tier: ``tax_export`` (PRO only). Service-level guard raises
    `TierFeatureUnavailable`; translated to 403 here.

    Query params:
        * ``account_id`` — scope to a single owned account.
        * ``tax_year`` — narrow to one sale-year.
        * ``apply_wash_sales`` — opt-in wash-sale post-pass.
    """
    service = TaxReportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_form_8949_csv(
            account_id=account_id,
            tax_year=tax_year,
            apply_wash_sales=apply_wash_sales,
        )
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("form8949"),
    )


@router.get("/schedule_d.csv")
async def export_schedule_d(
    db: DbDep,
    user: UserDep,
    account_id: int | None = Query(default=None),
    tax_year: int | None = Query(default=None),
) -> Response:
    """Export Schedule D-style annual rollup as CSV.

    Tier: ``tax_export`` (PRO only). One row per tax year present in
    the matched-pair set; ``tax_year`` narrows to a single year.
    """
    service = TaxReportService(db, user)  # type: ignore[arg-type]
    try:
        csv_bytes = await service.export_year_summary_csv(
            account_id=account_id,
            tax_year=tax_year,
        )
    except TierFeatureUnavailable as exc:
        raise _translate_tier(exc) from exc
    return Response(
        content=csv_bytes,
        media_type=_MEDIA_TYPE,
        headers=_disposition("schedule_d"),
    )


__all__ = ["router"]
