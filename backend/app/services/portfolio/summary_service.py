"""PortfolioSummaryService — user / account wide P&L roll-up.

Spec §5.2 / §7.4 / §7.5. Pulls position rows, batch-fetches quotes via
the injected `LivePriceFetcher`, then delegates the actual aggregate
math to `pnl.summarize()` so the domain layer remains the single
source of truth for portfolio totals.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.modules.portfolio.pnl import PortfolioSummary, summarize
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.services.portfolio.exceptions import PortfolioAccountNotFound

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.position import PortfolioPosition
    from app.models.user import User


class PortfolioSummaryService:
    """KPI aggregator. Always returns a `PortfolioSummary` — even for
    an empty portfolio (all zeros).
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

    async def get_user_summary(self) -> PortfolioSummary:
        """KPI row across every account owned by the user."""
        positions = await self._position_repo.list_by_user(self._user.id)
        return await self._summarize(positions)

    async def get_account_summary(self, account_id: int) -> PortfolioSummary:
        """KPI row for one account. Verifies ownership."""
        account = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )
        positions = await self._position_repo.list_by_account(account_id)
        return await self._summarize(positions)

    # ── internals ──────────────────────────────────────────────────────

    async def _summarize(
        self, positions: list[PortfolioPosition]
    ) -> PortfolioSummary:
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
        open_positions = [
            p for p in positions if (p.quantity or Decimal("0")) > Decimal("0")
        ]
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
