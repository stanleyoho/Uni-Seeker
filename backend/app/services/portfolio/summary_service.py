"""PortfolioSummaryService — user / account wide P&L roll-up.

Spec §5.2 / §7.4 / §7.5. Pulls position rows, batch-fetches quotes via
the injected `LivePriceFetcher`, then delegates the actual aggregate
math to `pnl.summarize()` so the domain layer remains the single
source of truth for portfolio totals.

Phase 4+ — multi-currency:
  `get_user_summary_multi_currency(base_currency=...)` buckets positions
  by their `currency` column, summarizes each bucket independently in its
  native currency, then converts to `base_currency` via the injected
  `FxService`. Tier gate (`multi_currency_summary`) is enforced inside
  the service when more than one currency is present so API callers don't
  need to pre-flight check.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.config import settings
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.modules.portfolio.pnl import (
    MultiCurrencyPortfolioSummary,
    PortfolioSummary,
    summarize,
)
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    TierFeatureUnavailable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.position import PortfolioPosition
    from app.models.user import User
    from app.services.portfolio.fx_service import FxService


_ZERO = Decimal("0")


class PortfolioSummaryService:
    """KPI aggregator. Always returns a `PortfolioSummary` — even for
    an empty portfolio (all zeros).

    Phase 4+: when `fx_service` is provided, `get_user_summary_multi_currency`
    can aggregate across currencies; otherwise the original same-currency
    path remains (backwards-compatible default).
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        live_price_fetcher: LivePriceFetcher,
        fx_service: FxService | None = None,
    ) -> None:
        self._db = db
        self._user = user
        self._fetcher = live_price_fetcher
        self._fx = fx_service
        self._account_repo = PortfolioAccountRepo(db)
        self._position_repo = PortfolioPositionRepo(db)

    async def get_user_summary(self) -> PortfolioSummary:
        """KPI row across every account owned by the user (same-currency)."""
        positions = await self._position_repo.list_by_user(self._user.id)
        return await self._summarize(positions)

    async def get_account_summary(self, account_id: int) -> PortfolioSummary:
        """KPI row for one account. Verifies ownership."""
        account = await self._account_repo.get_by_id(account_id, user_id=self._user.id)
        if account is None:
            raise PortfolioAccountNotFound(f"account {account_id} not found or not owned")
        positions = await self._position_repo.list_by_account(account_id)
        return await self._summarize(positions)

    # ── Phase 4+: multi-currency ──────────────────────────────────────────

    async def get_user_summary_multi_currency(
        self,
        base_currency: str = "TWD",
    ) -> MultiCurrencyPortfolioSummary:
        """Cross-currency KPI roll-up converted to `base_currency`.

        Tier gating:
          - If positions span more than one currency, the user MUST have
            the `multi_currency_summary` feature flag. Single-currency
            portfolios (e.g. only TWD) skip the tier check — they
            degrade gracefully to the regular same-currency path.
          - `enable_monetization=False` bypasses the check entirely.

        Behaviour:
          - Empty portfolio → all-zero summary with empty per-currency dict.
          - All positions in `base_currency` → trivial path, no FX calls.
          - Mixed currencies → bucket → summarize per bucket → convert
            base totals via `FxService.get_rates_for_currencies`.

        Raises:
            TierFeatureUnavailable: when multi-currency without the feature.
            RuntimeError: when `fx_service` was not injected but we need it.
        """
        base = base_currency.upper()
        positions = await self._position_repo.list_by_user(self._user.id)

        if not positions:
            return self._empty_multi(base)

        open_positions = [p for p in positions if (p.quantity or _ZERO) > _ZERO]
        if not open_positions:
            return self._empty_multi(base)

        # Bucket by currency. Account currency takes precedence if the
        # position row doesn't carry one (defensive — schema has the column
        # but legacy rows may be NULL).
        buckets: dict[str, list[PortfolioPosition]] = {}
        for p in open_positions:
            ccy = (p.currency or "TWD").upper()
            buckets.setdefault(ccy, []).append(p)

        # Tier gate: only when truly multi-currency.
        if (
            len(buckets) > 1
            and settings.enable_monetization
            and not has_feature(self._user.tier, "multi_currency_summary")
        ):
            raise TierFeatureUnavailable(feature="multi_currency_summary")

        # Single-currency fast path → no FX involved.
        if len(buckets) == 1 and base in buckets:
            summary = await self._summarize(open_positions)
            return MultiCurrencyPortfolioSummary(
                base_currency=base,
                summary=summary,
                by_currency_native={base: summary},
                by_currency_in_base={
                    base: (summary.total_cost, summary.total_value),
                },
                rates_used={base: Decimal("1")},
            )

        # Multi-currency path — need FX.
        if self._fx is None:
            raise RuntimeError("FxService is required for multi-currency summary")

        # Per-bucket native summary.
        native: dict[str, PortfolioSummary] = {}
        for ccy, positions_in_ccy in buckets.items():
            native[ccy] = await self._summarize(positions_in_ccy)

        # Fetch rates in one shot.
        rates = await self._fx.get_rates_for_currencies(
            currencies=set(buckets.keys()),
            base=base,
        )

        # Convert each bucket's totals into base.
        by_in_base: dict[str, tuple[Decimal, Decimal]] = {}
        total_cost = _ZERO
        total_value = _ZERO
        total_unrealized = _ZERO
        total_daily = _ZERO
        for ccy, s in native.items():
            rate = rates[ccy]
            cost_b = s.total_cost * rate
            value_b = s.total_value * rate
            unrl_b = s.total_unrealized_pnl * rate
            daily_b = s.total_daily_change * rate
            by_in_base[ccy] = (cost_b, value_b)
            total_cost += cost_b
            total_value += value_b
            total_unrealized += unrl_b
            total_daily += daily_b

        gain_simple = total_value - total_cost
        gain_simple_pct = gain_simple / total_cost if total_cost != _ZERO else _ZERO
        merged = PortfolioSummary(
            total_cost=total_cost,
            total_value=total_value,
            total_unrealized_pnl=total_unrealized,
            total_daily_change=total_daily,
            gain_simple=gain_simple,
            gain_simple_pct=gain_simple_pct,
        )
        return MultiCurrencyPortfolioSummary(
            base_currency=base,
            summary=merged,
            by_currency_native=native,
            by_currency_in_base=by_in_base,
            rates_used=rates,
        )

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _empty_multi(base: str) -> MultiCurrencyPortfolioSummary:
        zero_summary = summarize([])
        return MultiCurrencyPortfolioSummary(
            base_currency=base,
            summary=zero_summary,
            by_currency_native={},
            by_currency_in_base={},
            rates_used={},
        )

    async def _summarize(self, positions: list[PortfolioPosition]) -> PortfolioSummary:
        """Project (qty, avg_cost, last_price, prev_close) per position
        and delegate to the domain summarize().

        Closed positions (qty == 0) are dropped before computing
        `gain_simple` per spec §7.4 ("counting only currently-held
        positions"). Missing quotes are treated as last_price = avg_cost
        (zero unrealized) so the summary doesn't show NaN — this is a
        deliberate conservative choice; per-position view in
        `PositionWithPnL` still surfaces ``last_price=None`` so the UI
        can flag those rows.
        """
        if not positions:
            return summarize([])

        # Filter open before fetching to avoid wasting a quote on closed
        # rows. We do not drop the symbol entirely (other open positions
        # may share it across accounts).
        open_positions = [p for p in positions if (p.quantity or Decimal("0")) > Decimal("0")]
        if not open_positions:
            return summarize([])

        symbols = sorted({p.symbol for p in open_positions})
        quotes = await self._fetcher.fetch_quotes(symbols)

        rows: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        for p in open_positions:
            qty = p.quantity or Decimal("0")
            avg = p.avg_cost_fifo or Decimal("0")
            quote = quotes.get(p.symbol)
            if quote is None:
                # Missing quote: treat last_price = prev_close = avg_cost
                # so unrealized and daily change both contribute 0. The
                # row still affects total_cost (and therefore gain_simple
                # weighting) which keeps cost-based KPIs sane.
                last_price = avg
                prev_close = avg
            else:
                last_price = quote.last_price
                prev_close = quote.prev_close
            rows.append((qty, avg, last_price, prev_close))

        return summarize(rows)


__all__ = ["PortfolioSummaryService"]
