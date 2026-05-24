"""Summary endpoints — /api/v1/holdings/summary.

Spec §5.4 + §7.4. Returns user-wide or per-account KPI rows. The
domain `PortfolioSummary` has six numeric fields; we augment with
`position_count` + `account_count` for frontend convenience.

Phase 4+ — multi-currency:
  `GET /summary?base_currency=TWD` aggregates across currencies. When the
  user's positions span >1 currency, the `multi_currency_summary` feature
  flag is required (Pro tier only). Single-currency portfolios are
  unaffected so Free / Basic tiers keep working.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_serializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_fx_service, get_live_price_fetcher
from app.auth import require_auth
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.schemas.holdings.summary import SummaryResponse
from app.services.portfolio import PortfolioSummaryService
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)
from app.services.portfolio.fx_service import FxRateUnavailable, FxService

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]
FxDep = Annotated[FxService, Depends(get_fx_service)]


_SUPPORTED_BASE_CURRENCIES = frozenset({"TWD", "USD", "JPY", "HKD", "EUR", "GBP", "CNY"})


class CurrencyBreakdown(BaseModel):
    """Per-currency slice for the multi-currency response."""

    currency: str
    total_cost_native: Decimal
    total_value_native: Decimal
    total_cost_in_base: Decimal
    total_value_in_base: Decimal
    rate_to_base: Decimal

    @field_serializer(
        "total_cost_native",
        "total_value_native",
        "total_cost_in_base",
        "total_value_in_base",
        "rate_to_base",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal) -> str:
        return str(value)


class MultiCurrencySummaryResponse(SummaryResponse):
    """Extends SummaryResponse with the per-currency breakdown."""

    base_currency: str
    by_currency: list[CurrencyBreakdown]


@router.get("/summary")
async def get_user_summary(
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
    fx: FxDep,
    base_currency: Annotated[
        str | None,
        Query(
            description=(
                "ISO 4217 base currency for cross-currency aggregation. "
                "Omit for legacy same-currency response."
            ),
            max_length=10,
        ),
    ] = None,
) -> SummaryResponse | MultiCurrencySummaryResponse:
    """KPI row aggregated across every account the user owns.

    When `base_currency` is omitted, returns the legacy
    `SummaryResponse` (same-currency aggregation; backwards-compatible
    with existing clients).

    When `base_currency` is provided, returns
    `MultiCurrencySummaryResponse` with cross-currency totals expressed
    in the requested base, plus a per-currency breakdown for chart
    rendering. Requires the `multi_currency_summary` feature flag if
    positions span more than one currency.
    """
    if base_currency is None:
        # Legacy single-currency path — no FX involved.
        service = PortfolioSummaryService(db, user, fetcher)  # type: ignore[arg-type]
        summary = await service.get_user_summary()
        position_count = await PortfolioPositionRepo(db).count_by_user(
            user.id  # type: ignore[attr-defined]
        )
        account_count = await PortfolioAccountRepo(db).count_by_user(
            user.id  # type: ignore[attr-defined]
        )
        return SummaryResponse(
            total_cost=summary.total_cost,
            total_value=summary.total_value,
            total_unrealized_pnl=summary.total_unrealized_pnl,
            total_daily_change=summary.total_daily_change,
            gain_simple=summary.gain_simple,
            gain_simple_pct=summary.gain_simple_pct,
            position_count=position_count,
            account_count=account_count,
        )

    base_u = base_currency.upper()
    if base_u not in _SUPPORTED_BASE_CURRENCIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported_base_currency:{base_u}",
        )

    service = PortfolioSummaryService(db, user, fetcher, fx_service=fx)  # type: ignore[arg-type]
    try:
        multi = await service.get_user_summary_multi_currency(base_currency=base_u)
    except TierFeatureUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except FxRateUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"fx_rate_unavailable:{exc.base}_{exc.quote}",
        ) from exc

    position_count = await PortfolioPositionRepo(db).count_by_user(
        user.id  # type: ignore[attr-defined]
    )
    account_count = await PortfolioAccountRepo(db).count_by_user(
        user.id  # type: ignore[attr-defined]
    )

    breakdown: list[CurrencyBreakdown] = []
    for ccy, native in multi.by_currency_native.items():
        cost_b, value_b = multi.by_currency_in_base.get(ccy, (Decimal("0"), Decimal("0")))
        breakdown.append(
            CurrencyBreakdown(
                currency=ccy,
                total_cost_native=native.total_cost,
                total_value_native=native.total_value,
                total_cost_in_base=cost_b,
                total_value_in_base=value_b,
                rate_to_base=multi.rates_used.get(ccy, Decimal("1")),
            )
        )

    return MultiCurrencySummaryResponse(
        total_cost=multi.summary.total_cost,
        total_value=multi.summary.total_value,
        total_unrealized_pnl=multi.summary.total_unrealized_pnl,
        total_daily_change=multi.summary.total_daily_change,
        gain_simple=multi.summary.gain_simple,
        gain_simple_pct=multi.summary.gain_simple_pct,
        position_count=position_count,
        account_count=account_count,
        base_currency=multi.base_currency,
        by_currency=breakdown,
    )


@router.get(
    "/summary/{account_id}",
    response_model=SummaryResponse,
)
async def get_account_summary(
    account_id: int,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> SummaryResponse:
    """KPI row scoped to one of the user's accounts; 404 when missing
    / not owned."""
    service = PortfolioSummaryService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        summary = await service.get_account_summary(account_id)
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    # For per-account summary, position count is scoped to the account.
    positions = await PortfolioPositionRepo(db).list_by_account(account_id)
    return SummaryResponse(
        total_cost=summary.total_cost,
        total_value=summary.total_value,
        total_unrealized_pnl=summary.total_unrealized_pnl,
        total_daily_change=summary.total_daily_change,
        gain_simple=summary.gain_simple,
        gain_simple_pct=summary.gain_simple_pct,
        position_count=len(positions),
        account_count=1,
    )
