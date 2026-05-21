"""PortfolioPositionService — position roll-ups enriched with live P&L.

Spec §5.2 / §7.1 / §7.3. This service is read-only: it pulls position
rows from `PortfolioPositionRepo`, batch-fetches live quotes through the
injected `LivePriceFetcher` Protocol, and uses `pnl.unrealized` /
`pnl.daily_change` from the domain layer to compute per-position
unrealized P&L + daily change.

LivePriceFetcher injection pattern (constructor, not per-call):
- One fetcher instance is owned by the service for its (request) lifetime.
- API layer wires the fetcher via FastAPI Depends; tests inject a
  MockLivePriceFetcher.
- This keeps the call sites clean (`svc.list_positions()`) and lets the
  fetcher hold its own batch cache without changing the public API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.portfolio.live_price_fetcher import LivePriceFetcher
from app.modules.portfolio.pnl import DailyChange, UnrealizedPnL, daily_change, unrealized
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioPositionRepo,
)
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.position import PortfolioPosition
    from app.models.enums import Market
    from app.models.user import User


@dataclass
class PositionWithPnL:
    """One position row enriched with live price + computed P&L.

    Decimal-as-string is the API contract (project CLAUDE.md), but at
    the service boundary we keep Decimal — schema layer will str()
    them. ``last_price`` may be ``None`` when the symbol has no
    `stock_prices` history (spec §12 R8).
    """

    account_id: int
    symbol: str
    market: Market
    currency: str
    quantity: Decimal
    avg_cost: Decimal | None
    total_cost: Decimal | None
    realized_pnl: Decimal
    is_closed: bool
    last_price: Decimal | None
    prev_close: Decimal | None
    price_as_of: datetime | None
    unrealized_pnl: UnrealizedPnL | None
    daily_change: DailyChange | None


class PortfolioPositionService:
    """Read-only position + P&L composition service."""

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

    # ── public API ──────────────────────────────────────────────────────

    async def list_positions(
        self, account_id: int | None = None
    ) -> list[PositionWithPnL]:
        """All positions visible to the requesting user.

        Args:
            account_id: when provided, restrict to one account
                (verifying ownership). Otherwise aggregates across all
                of the user's accounts.

        Returns:
            List of `PositionWithPnL`. Closed positions (qty=0) are
            included so the API layer / UI can decide whether to hide
            them — service layer does NOT filter on `is_closed`.
        """
        if account_id is not None:
            await self._require_owned_account(account_id)
            positions = await self._position_repo.list_by_account(account_id)
        else:
            positions = await self._position_repo.list_by_user(self._user.id)

        return await self._enrich_with_pnl(positions)

    async def get_position(
        self, account_id: int, symbol: str, market: Market
    ) -> PositionWithPnL:
        """Fetch one enriched position. Verifies account ownership."""
        await self._require_owned_account(account_id)
        pos = await self._position_repo.get(account_id, symbol, market=market)
        if pos is None:
            # Returning a synthetic "empty" object would confuse the
            # API layer; raise 404 instead.
            raise PortfolioAccountNotFound(
                f"position {symbol}/{market} on account {account_id} not found"
            )
        enriched = await self._enrich_with_pnl([pos])
        return enriched[0]

    # ── internals ──────────────────────────────────────────────────────

    async def _require_owned_account(self, account_id: int) -> None:
        account = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

    async def _enrich_with_pnl(
        self, positions: list[PortfolioPosition]
    ) -> list[PositionWithPnL]:
        """Batch-fetch quotes for the distinct symbols, then compose
        unrealized + daily change per row. Symbols absent from the
        quote dict are surfaced with `last_price=None` (§12 R8).
        """
        if not positions:
            return []

        symbols = sorted({p.symbol for p in positions})
        quotes = await self._fetcher.fetch_quotes(symbols)

        out: list[PositionWithPnL] = []
        for p in positions:
            qty = p.quantity or Decimal("0")
            avg = p.avg_cost_fifo
            quote = quotes.get(p.symbol)
            if quote is None:
                out.append(
                    PositionWithPnL(
                        account_id=p.account_id,
                        symbol=p.symbol,
                        market=p.market,
                        currency=p.currency,
                        quantity=qty,
                        avg_cost=avg,
                        total_cost=p.total_cost,
                        realized_pnl=p.realized_pnl or Decimal("0"),
                        is_closed=bool(p.is_closed),
                        last_price=None,
                        prev_close=None,
                        price_as_of=None,
                        unrealized_pnl=None,
                        daily_change=None,
                    )
                )
                continue

            avg_for_calc = avg if avg is not None else Decimal("0")
            out.append(
                PositionWithPnL(
                    account_id=p.account_id,
                    symbol=p.symbol,
                    market=p.market,
                    currency=p.currency,
                    quantity=qty,
                    avg_cost=avg,
                    total_cost=p.total_cost,
                    realized_pnl=p.realized_pnl or Decimal("0"),
                    is_closed=bool(p.is_closed),
                    last_price=quote.last_price,
                    prev_close=quote.prev_close,
                    price_as_of=quote.as_of,
                    unrealized_pnl=unrealized(
                        qty=qty,
                        avg_cost=avg_for_calc,
                        last_price=quote.last_price,
                    ),
                    daily_change=daily_change(
                        qty=qty,
                        last_price=quote.last_price,
                        prev_close=quote.prev_close,
                    ),
                )
            )
        return out


__all__ = [
    "PortfolioPositionService",
    "PositionWithPnL",
]
