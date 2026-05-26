"""Portfolio rebalancing endpoints — /api/v1/holdings/rebalance/*.

Spec: Portfolio Phase 5+. Pro-tier only.

Two endpoints, sharing one ``RebalanceRequest`` body shape:

- ``POST /preview`` — read-only: computes ``suggested_trades`` and
  returns them. No DB writes. The UI can show the plan to the user
  before they commit.
- ``POST /execute`` (Phase 2) — server re-computes the same plan via
  ``RebalancingService.preview_rebalance``, then writes each suggested
  trade through the existing ``PortfolioTradeService.record_trade``
  pipeline. **Per-trade independent commit**: each trade is its own
  transaction, the response carries ``executed`` / ``skipped`` / ``failed``
  lists so a single bad row doesn't poison the whole batch.

Tier gating uses the standard 双保险 pattern (spec §9):
  - ``Depends(tier_guard(feature="rebalancing"))`` short-circuits with 403
    before the service even runs.
  - Inside ``RebalancingService.preview_rebalance`` the same flag is
    re-asserted; if the dependency were ever forgotten, this raises
    ``TierFeatureUnavailable`` which we translate to 403 with the
    standard ``feature_unavailable:rebalancing`` detail string.

Out of scope for the Phase 2 execute endpoint (Stanley 2026-05-24):
  - Idempotency key. Personal-scale trading rarely double-posts; the
    cost of duplicate handling outweighs the benefit. Can be added in
    Phase 3+ when this is opened to a multi-user workload.
  - Client-passed ``suggested_trades`` list. Avoids the contract
    complexity of two sources of truth + drift between the preview
    snapshot and the execute snapshot. Server always re-computes.
  - Broker API integration. This endpoint records "what the user did";
    actually placing the order at a broker is a separate concern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import require_auth
from app.models.enums import Market
from app.modules.billing.tier_limits import tier_guard
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.schemas.holdings.rebalance import (
    ExecutedTrade,
    FailedTrade,
    RebalanceExecuteResponse,
    RebalanceRequest,
    RebalanceResponse,
    SkippedTrade,
    SuggestedTradeResponse,
)
from app.services.portfolio.exceptions import (
    InsufficientShares,
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
    TierLimitExceeded,
)
from app.services.portfolio.rebalancing_service import RebalancingService
from app.services.portfolio.trade_service import PortfolioTradeService

router = APIRouter(prefix="/rebalance", tags=["holdings.rebalance"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]
FetcherDep = Annotated[LivePriceFetcher, Depends(get_live_price_fetcher)]


@router.post(
    "/preview",
    response_model=RebalanceResponse,
    dependencies=[Depends(tier_guard(feature="rebalancing"))],
)
async def preview_rebalance(
    body: RebalanceRequest,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> RebalanceResponse:
    """Compute the trades required to reach ``body.targets``.

    Errors:
        - 403 ``feature_unavailable:rebalancing`` when the user's tier
          lacks the feature flag (the guard catches this first; the
          inner assert is the backup).
        - 404 ``portfolio_account_not_found`` when ``account_id`` is set
          and not owned by the user.
        - 422 ``invalid_rebalance_input`` when targets fail validation
          (sum != 100, duplicates, negatives, etc.).
    """
    service = RebalancingService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        result = await service.preview_rebalance(
            targets=[t.model_dump() for t in body.targets],
            account_id=body.account_id,
            min_trade_value=body.min_trade_value,
        )
    except TierFeatureUnavailable as exc:
        # Defensive: should be caught by the dependency above. Keep the
        # translation so a future refactor (e.g. swapping the dep out)
        # still returns the right status.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        # Raised by ``validate_targets``: sum mismatch, negatives, dupes.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_rebalance_input",
        ) from exc

    # Translate domain dataclasses → Pydantic response.
    return RebalanceResponse(
        total_portfolio_value=result.total_portfolio_value,
        suggested_trades=[
            SuggestedTradeResponse(
                symbol=t.symbol,
                market=t.market,  # str → Market via use_enum_values
                action=t.action,
                qty=t.qty,
                estimated_price=t.estimated_price,
                estimated_value=t.estimated_value,
                rationale=t.rationale,
                account_id=t.account_id,
            )
            for t in result.suggested_trades
        ],
        final_allocation_pct=result.final_allocation_pct,
        skipped_trades=result.skipped_trades,
        cash_residual=result.cash_residual,
    )


@router.post(
    "/execute",
    response_model=RebalanceExecuteResponse,
    dependencies=[Depends(tier_guard(feature="rebalancing"))],
)
async def execute_rebalance(
    body: RebalanceRequest,
    db: DbDep,
    user: UserDep,
    fetcher: FetcherDep,
) -> RebalanceExecuteResponse:
    """Re-compute the rebalance plan and persist every suggested trade.

    Path c.i (Stanley 拍板 2026-05-24): the server re-computes
    ``suggested_trades`` from the same ``targets`` payload as ``/preview``
    (no client-passed trade list) and then writes each one through the
    same ``PortfolioTradeService.record_trade`` pipeline that backs
    ``POST /holdings/trades``.

    Per-trade independent commit:
        Each suggested trade is its own try-block. If the trade-write
        layer rejects one row (e.g. ``InsufficientShares`` because the
        live position drifted since the snapshot was taken), it lands in
        ``failed`` and the next row continues. The endpoint returns 200
        with a per-row summary; the client decides how to react.

    Multi-account dispatch (Phase 3):
        - ``body.account_id`` is now optional. When set, every trade is
          routed to that one account (back-compat with Phase 2 behavior).
        - When omitted (aggregate mode), each trade is routed to the
          account_id carried on the planner-emitted ``SuggestedTrade``.
          That field is derived from the source position the planner
          loaded — by construction it only contains accounts the user
          owns (the planner sources from ``list_by_user``).
        - If the planner produced any trade with ``account_id=None``
          (a brand-new BUY symbol with no source position to derive
          from) AND no top-level scope was given, we 422 the whole
          batch — partial execute of an unroutable plan would silently
          drop work.
        - Defense-in-depth: each unique account_id in the resolved plan
          is re-validated via ``_require_owned_account`` before any
          trade lands; a foreign id surfaces as 404 (consistent with
          the rest of /holdings/*, see spec §9.5).

    Errors (whole-batch — bubble like preview):
        - 403 ``feature_unavailable:rebalancing`` for non-Pro tiers.
        - 404 ``portfolio_account_not_found`` when ``account_id`` is set
          and not owned, OR when a defense-in-depth re-check on a
          resolved per-trade account_id fails.
        - 422 ``invalid_rebalance_input`` for bad ``targets`` (sum
          mismatch, duplicates, negatives).
        - 422 ``account_unresolved_for_trade`` when aggregate mode
          (top-level ``account_id`` omitted) produces a plan with any
          un-routed BUY — the client must rescope before executing.
    """
    rebalance_svc = RebalancingService(db, user, fetcher)  # type: ignore[arg-type]
    try:
        plan = await rebalance_svc.preview_rebalance(
            targets=[t.model_dump() for t in body.targets],
            account_id=body.account_id,
            min_trade_value=body.min_trade_value,
        )
    except TierFeatureUnavailable as exc:
        # Defensive — the dependency above should already 403.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.feature_unavailable(exc.feature),
        ) from exc
    except PortfolioAccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_rebalance_input",
        ) from exc

    # ── resolve per-trade target accounts (Phase 3) ────────────────────
    # Pre-flight: if aggregate mode and any suggested trade has no
    # account_id (brand-new BUY symbol absent from every account), reject
    # the whole batch with a clear 422. Partial execution would silently
    # drop those rows — worse UX than a re-scope prompt.
    unresolved = [f"{t.symbol}|{t.market}" for t in plan.suggested_trades if t.account_id is None]
    if unresolved and body.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="account_unresolved_for_trade",
        )

    # Defense-in-depth: re-validate every distinct resolved account_id
    # is owned by the user. The planner sources only from list_by_user,
    # so this is structurally already true — but the check is cheap and
    # protects against a future refactor that loosens that invariant.
    trade_svc = PortfolioTradeService(db, user)  # type: ignore[arg-type]
    distinct_accounts = {t.account_id for t in plan.suggested_trades if t.account_id is not None}
    for resolved_aid in distinct_accounts:
        try:
            await trade_svc._require_owned_account(resolved_aid)
        except PortfolioAccountNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail.ACCOUNT_NOT_FOUND,
            ) from exc

    executed: list[ExecutedTrade] = []
    failed: list[FailedTrade] = []
    total_executed_value = Decimal("0")
    today = datetime.now(tz=UTC).date()

    for trade in plan.suggested_trades:
        # Resolve this trade's destination account: per-trade if set
        # (aggregate mode), else top-level scope (single-account mode).
        # The pre-flight above guarantees this is always int by here.
        target_account_id = trade.account_id or body.account_id
        assert target_account_id is not None
        # Coerce the domain layer's str-market back to the Market enum
        # the trade service expects. The pure module is enum-agnostic so
        # it hands us a string; ``Market(str)`` works because Market is
        # ``str, enum.Enum`` (see app/models/enums.py:6).
        try:
            market_enum = Market(trade.market)
        except ValueError as exc:
            # Unknown market string — should never happen if positions
            # came out of our own DB, but be defensive.
            failed.append(
                FailedTrade(
                    symbol=trade.symbol,
                    market=Market.TW_TWSE,  # placeholder for the wire schema
                    action=trade.action,
                    error_code="invalid_market",
                    message=str(exc),
                    account_id=target_account_id,
                )
            )
            continue

        try:
            persisted = await trade_svc.record_trade(
                account_id=target_account_id,
                action=trade.action,
                symbol=trade.symbol,
                market=market_enum,
                qty=trade.qty,
                price=trade.estimated_price,
                trade_date=today,
                note=f"rebalance: {trade.rationale}",
            )
            await db.commit()
            await db.refresh(persisted)
        except InsufficientShares as exc:
            await db.rollback()
            failed.append(
                FailedTrade(
                    symbol=trade.symbol,
                    market=market_enum,
                    action=trade.action,
                    error_code=detail.INSUFFICIENT_SHARES,
                    message=str(exc),
                    account_id=target_account_id,
                )
            )
            continue
        except TierLimitExceeded as exc:
            # Trade-month quota or positions quota tripped mid-batch.
            # Surface as failed and stop — subsequent rows would hit the
            # same wall. (Multi-account caveat: the cap is per-user, not
            # per-account, so even other accounts can't bail us out.)
            await db.rollback()
            failed.append(
                FailedTrade(
                    symbol=trade.symbol,
                    market=market_enum,
                    action=trade.action,
                    error_code=detail.limit_exceeded(exc.limit_key),
                    message=str(exc),
                    account_id=target_account_id,
                )
            )
            break
        except ValueError as exc:
            await db.rollback()
            failed.append(
                FailedTrade(
                    symbol=trade.symbol,
                    market=market_enum,
                    action=trade.action,
                    error_code=detail.INVALID_TRADE_INPUT,
                    message=str(exc),
                    account_id=target_account_id,
                )
            )
            continue

        executed.append(
            ExecutedTrade(
                symbol=trade.symbol,
                market=market_enum,
                action=trade.action,
                qty=trade.qty,
                price=trade.estimated_price,
                trade_id=persisted.id,
                account_id=target_account_id,
            )
        )
        total_executed_value += trade.qty * trade.estimated_price

    # Translate the planner's skip dicts → typed wire schema.
    skipped: list[SkippedTrade] = [
        SkippedTrade(
            symbol=s.get("symbol", ""),
            market=str(s.get("market", "")),
            reason=str(s.get("reason", "unknown")),
            target_pct=s.get("target_pct"),
            delta_value=s.get("delta_value"),
        )
        for s in plan.skipped_trades
    ]

    return RebalanceExecuteResponse(
        executed=executed,
        skipped=skipped,
        failed=failed,
        total_executed_value=total_executed_value,
    )


__all__ = ["router"]
