"""RebalancingService — Pro-tier portfolio rebalancing planner.

Spec: Portfolio Phase 5+ rebalancing tool. Given a target allocation, the
service loads the user's current open positions, fetches live prices via
the injected ``LivePriceFetcher``, and delegates the actual math to the
pure ``rebalancing`` domain module.

Tier gating (spec §9 双保险):
  - Endpoint-level: ``tier_guard(feature="rebalancing")`` rejects the
    request before the service is even constructed.
  - Service-level: ``_assert_feature`` is a second line in case a future
    caller (CLI / batch job) forgets the FastAPI dependency. Raises
    ``TierFeatureUnavailable`` which the API layer maps to 403.

Audit trail:
  - Every preview emits a ``portfolio.rebalance_previewed`` audit event
    (no destructive action — but the user did just see actionable trade
    suggestions; we want a record of what was proposed when).

Phase 1 scope:
  - **preview only.** No ``execute_rebalance`` — Phase 2+ may add that
    on top of ``trade_service.record_trade``. The preview / execute
    split lets the frontend confirm with the user before any DB writes.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.modules.portfolio.rebalancing import (
    CurrentPosition,
    RebalanceResult,
    TargetAllocation,
    compute_rebalance,
)
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.services.audit import log_audit_event
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


_ZERO = Decimal("0")
_DEFAULT_MIN_TRADE_VALUE = Decimal("100")


class RebalancingService:
    """Async service for rebalancing previews.

    Dependencies are injected at construction time so the service stays
    stateless across requests and easy to test (mock fetcher).
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        live_price_fetcher: LivePriceFetcher,
    ) -> None:
        self._db = db
        self._user = user
        self._fetcher = live_price_fetcher
        self._account_repo = PortfolioAccountRepo(db)
        self._position_repo = PortfolioPositionRepo(db)

    # ── tier guard (spec §9 second line) ────────────────────────────────

    def _assert_feature(self) -> None:
        """Raise TierFeatureUnavailable if the user can't use rebalancing.

        Bypassed when ``settings.enable_monetization`` is False, which is
        the test-mode behaviour everywhere else in the codebase.
        """
        if not settings.enable_monetization:
            return
        if not has_feature(self._user.tier, "rebalancing"):
            raise TierFeatureUnavailable(feature="rebalancing")

    # ── ownership helpers ──────────────────────────────────────────────

    async def _require_owned_account(self, account_id: int) -> None:
        account = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

    # ── public API ──────────────────────────────────────────────────────

    async def preview_rebalance(
        self,
        targets: list[dict[str, Any]],
        account_id: int | None = None,
        min_trade_value: Decimal = _DEFAULT_MIN_TRADE_VALUE,
    ) -> RebalanceResult:
        """Run a rebalancing preview for the user.

        Algorithm:
          1. Tier check — must have the ``rebalancing`` feature.
          2. Load current open positions, scoped to ``account_id`` if set.
          3. Batch-fetch live prices for the distinct symbols. Symbols
             without a quote keep a zero ``last_price`` — the pure
             module's "missing price" branch will surface them as skips
             with a ``missing_price_*`` rationale rather than crashing.
          4. Build domain dataclasses (``CurrentPosition`` /
             ``TargetAllocation``) and call ``compute_rebalance``.
          5. Emit an audit event so we can correlate UI activity later.

        Args:
            targets: List of ``{symbol, market, target_pct}`` dicts. The
                API layer passes the Pydantic-validated payload through
                ``.model_dump()`` here so the service stays Pydantic-free.
                ``market`` may be either a string code (``"TW_TWSE"``) or
                a ``Market`` enum value — both are coerced to ``.value``.
            account_id: Optional account scope. ``None`` aggregates across
                every account the user owns.
            min_trade_value: Skip-threshold for tiny rebalancing trades.

        Raises:
            TierFeatureUnavailable: when the user lacks the feature flag.
            PortfolioAccountNotFound: when ``account_id`` is not owned.
            ValueError: when ``targets`` fail validation
                (sum != 100, duplicates, negatives).
        """
        self._assert_feature()

        # ----- load positions ------------------------------------------------
        if account_id is not None:
            await self._require_owned_account(account_id)
            position_rows = await self._position_repo.list_by_account(
                account_id
            )
        else:
            position_rows = await self._position_repo.list_by_user(
                self._user.id
            )

        # Only open positions participate in rebalancing math.
        open_positions = [
            p for p in position_rows if (p.quantity or _ZERO) > _ZERO
        ]

        # ----- fetch live prices --------------------------------------------
        symbols = sorted({p.symbol for p in open_positions})
        quotes = await self._fetcher.fetch_quotes(symbols) if symbols else {}

        # Map ORM rows → domain dataclasses. Missing-quote symbols still
        # produce a CurrentPosition row (so the planner knows they exist)
        # but with last_price=0 → the pure module skips and reports.
        current_positions: list[CurrentPosition] = []
        for p in open_positions:
            qty = p.quantity or _ZERO
            quote = quotes.get(p.symbol)
            last_price = quote.last_price if quote is not None else _ZERO
            current_positions.append(
                CurrentPosition(
                    symbol=p.symbol,
                    market=_market_to_str(p.market),
                    qty=qty,
                    last_price=last_price,
                    current_value=qty * last_price,
                )
            )

        # ----- coerce request targets to domain dataclass -------------------
        target_objs: list[TargetAllocation] = [
            TargetAllocation(
                symbol=t["symbol"],
                market=_market_to_str(t["market"]),
                target_pct=Decimal(str(t["target_pct"])),
            )
            for t in targets
        ]

        # ----- delegate to the pure module ----------------------------------
        # NOTE: compute_rebalance() raises ValueError on invalid targets;
        # we let it bubble — the API layer translates to HTTP 422.
        result = compute_rebalance(
            positions=current_positions,
            targets=target_objs,
            min_trade_value=min_trade_value,
        )

        # ----- audit trail (best-effort; never blocks the preview) -----------
        await log_audit_event(
            self._db,
            action="portfolio.rebalance_previewed",
            user_id=self._user.id,
            resource_type="portfolio_rebalance",
            resource_id=str(account_id) if account_id is not None else "all",
            after_state={
                "account_id": account_id,
                "target_count": len(target_objs),
                "suggested_trade_count": len(result.suggested_trades),
                "skipped_count": len(result.skipped_trades),
                "total_portfolio_value": str(result.total_portfolio_value),
                "min_trade_value": str(min_trade_value),
            },
        )

        return result

    # NB: NO ``execute_rebalance`` in Phase 1. Phase 2+ would orchestrate
    # ``PortfolioTradeService.record_trade()`` per suggested trade behind
    # a ``dry_run`` flag — out of scope here.


# ── module-private helpers ──────────────────────────────────────────────


def _market_to_str(value: Any) -> str:
    """Normalize ``Market`` enum / string / other to a wire string.

    The pure module is enum-agnostic (works on strings). The ORM
    column is a ``Market`` enum, and the request payload arrives as a
    string. This shim handles both transparently without forcing the
    pure module to depend on the enum.
    """
    if isinstance(value, Market):
        return value.value
    return str(value)


__all__ = ["RebalancingService"]
