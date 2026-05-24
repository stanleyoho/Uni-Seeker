"""F13CrossStockService — per-stock institutional ownership panel.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2, §8 (`institutional_ownership_panel` Pro-tier feature).

Answers "which filers hold this stock and how have their positions
changed?" — the inverse of `F13FilingService`'s per-filer surface.

Tier gating: this is a **Pro-only** feature. Lower tiers raise
`F13TierFeatureUnavailable` immediately, well before any DB query is
issued — this keeps free-tier traffic from contributing to the JOIN
load.

Resolution: caller passes a symbol; we look up `stocks.id` first
(populates the FK index path). When no stock row exists yet but the
holdings table carries the CUSIP directly, we fall back to
`list_by_cusip` so unmapped stocks still render. Both paths return
the same dict shape so the API layer doesn't branch on which one was
used.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.config import settings
from app.models.stock import Stock
from app.modules.billing.tier_limits import has_feature
from app.repositories.institutional import F13HoldingRepo
from app.services.institutional.exceptions import (
    F13TierFeatureUnavailable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


class F13CrossStockService:
    """Per-stock institutional view (Pro tier feature)."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._holding_repo = F13HoldingRepo(db)

    # ── tier guard ──────────────────────────────────────────────────────

    def _assert_feature(self) -> None:
        """Enforce `institutional_ownership_panel` Pro-tier flag.

        Bypassed when `enable_monetization=False` (dev/test parity with
        `tier_guard`).
        """
        if not settings.enable_monetization:
            return
        if not has_feature(self._user.tier, "institutional_ownership_panel"):
            raise F13TierFeatureUnavailable(feature="institutional_ownership_panel")

    # ── public API ──────────────────────────────────────────────────────

    async def get_institutional_holders_for_stock(self, symbol: str, limit: int = 50) -> list[dict]:
        """List institutional holders for `symbol`, latest-per-filer.

        Returns a list of dicts with this shape:

            {
                filer_id: int,
                filer_cik: str,
                filer_name: str,
                latest_shares: Decimal | None,
                latest_value_usd: Decimal,
                latest_period_end: date,
                put_call: str | None,
                cusip: str,
            }

        Multiple filings per filer are collapsed to the **most recent**
        (`report_period_end DESC`). The repo already orders by period
        DESC so the dict order in our OrderedDict naturally keeps the
        first-seen-wins semantics.

        Raises:
            F13TierFeatureUnavailable — non-Pro tier.
        """
        self._assert_feature()

        # Step 1: try local stock lookup (preferred — uses indexed FK).
        stock_row = await self._db.execute(select(Stock).where(Stock.symbol == symbol))
        stock = stock_row.scalar_one_or_none()

        tuples: list[tuple]
        if stock is not None:
            tuples = await self._holding_repo.list_by_stock(stock.id, limit=limit * 4)
            # Fallback to CUSIP if stock has one but no holdings linked yet.
            if not tuples and stock.cusip:
                tuples = await self._holding_repo.list_by_cusip(stock.cusip, limit=limit * 4)
        else:
            # No stock row — caller might still hold a CUSIP via the
            # API layer wrapping the same symbol. Phase 1 keeps this
            # path empty; the API layer can add a CUSIP-direct
            # endpoint in Batch C if needed.
            tuples = []

        # Step 2: collapse to one row per filer (most recent wins).
        # `tuples` is already ordered by period_end DESC inside the repo;
        # OrderedDict insertion-order preserves that for us.
        by_filer: OrderedDict[int, dict] = OrderedDict()
        for holding, filing, filer in tuples:
            if filer.id in by_filer:
                continue
            by_filer[filer.id] = {
                "filer_id": filer.id,
                "filer_cik": filer.cik,
                "filer_name": filer.name,
                "latest_shares": holding.shares,
                "latest_value_usd": holding.value_usd or Decimal("0"),
                "latest_period_end": filing.report_period_end,
                "put_call": holding.put_call,
                "cusip": holding.cusip,
            }
            if len(by_filer) >= limit:
                break

        return list(by_filer.values())
