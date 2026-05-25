"""AnalyticsService — TWR / Sharpe / max-drawdown over snapshots.

Phase 5. Spec §11 (TWR / Sharpe extensibility) + §6 Table 6
(holdings_snapshots). Reads time-series from `holdings_snapshots`,
classifies trade rows from `portfolio_trades` as cash flows, and
delegates math to `app.modules.portfolio.analytics`.

Tier gate
---------
The proxy feature flag is **`daily_change_breakdown`** (per Phase 5
brief). Today that flag is Pro-only — Pro is the proxy for "advanced
analytics" until we shape a dedicated `advanced_analytics` feature.

Cash-flow classification (for TWR)
----------------------------------
The TWR sub-period math (`analytics.compute_twr`) wants `CashFlow`
records that mark external capital movements:

  * **BUY**     → positive flow (cash in)
  * **SELL**    → negative flow (cash out — proceeds taken out)
  * **DIVIDEND** → ignored (counts as portfolio earnings, not external
                   capital). If the user reinvests, the reinvestment
                   shows up as a separate BUY row, so this isn't a
                   double-count.
  * **SPLIT**   → ignored (no cash impact).

We compute `flow_amount ≈ qty × price + fee + tax`. For SELLs the sign
is negative: `-(qty × price - fee - tax)` (proceeds leaving the
portfolio). Both fee and tax are included in cost-basis sign on the
BUY side per spec §7.2.

Period resolution
-----------------
Periods are anchored on **today** (`date.today()`). For `"ytd"` we start
from Jan 1 of the current year; for `"all"` we use the earliest
snapshot date for the user (falling back to today minus 1 day when the
user has no snapshots, which gives the empty-analytics shape).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import and_, select

from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.trade import PortfolioTrade
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.analytics import (
    AnalyticsResult,
    CashFlow,
    NavSnapshot,
    compute_max_drawdown,
    compute_sharpe,
    compute_twr,
    daily_returns_from_navs,
)
from app.repositories.portfolio.account_repo import PortfolioAccountRepo
from app.repositories.portfolio.snapshot_repo import HoldingsSnapshotRepo
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFoundError,
    TierFeatureUnavailableError,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


Period = Literal["1m", "3m", "6m", "1y", "ytd", "all"]
_ZERO = Decimal("0")
_TIER_FEATURE = "daily_change_breakdown"


class AnalyticsService:
    """Orchestrates snapshot reads + analytics math.

    Constructor is symmetric with the other portfolio services
    (`PortfolioSummaryService`, ...): inject DB, user, fetcher. The
    `live_price_fetcher` is currently unused — kept for symmetry and
    forward-compat (analytics may later marry intraday prices with the
    most recent snapshot to estimate same-day TWR).
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        live_price_fetcher: object | None = None,
    ) -> None:
        self._db = db
        self._user = user
        self._fetcher = live_price_fetcher  # reserved
        self._snapshot_repo = HoldingsSnapshotRepo(db)
        self._account_repo = PortfolioAccountRepo(db)

    async def compute_period_analytics(
        self,
        period: Period = "1m",
        account_id: int | None = None,
    ) -> AnalyticsResult:
        """Compute TWR / Sharpe / max-drawdown over `period`.

        Raises:
            TierFeatureUnavailableError: user's tier lacks the proxy feature.
            PortfolioAccountNotFoundError: account filter given but not owned.
        """
        # 1) Tier gate (service-level double-check per spec §9).
        if not has_feature(self._user.tier, _TIER_FEATURE):
            raise TierFeatureUnavailableError(_TIER_FEATURE)

        # 2) Verify account ownership when caller asked to scope.
        if account_id is not None:
            owned = await self._account_repo.get_by_id(account_id, user_id=self._user.id)
            if owned is None:
                raise PortfolioAccountNotFoundError(f"account {account_id} not found or not owned")

        # 3) Resolve period window.
        date_to = date.today()
        date_from = await self._resolve_date_from(period, date_to, account_id)

        # 4) Load snapshots in range, ASC by date.
        snapshots = await self._snapshot_repo.list_by_user(
            user_id=self._user.id,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
        )

        nav_series = [
            NavSnapshot(
                snapshot_date=s.snapshot_date,
                total_value=s.total_value,
                total_cost=s.total_cost,
            )
            for s in snapshots
        ]

        # 5) Cash flows from trades in [date_from, date_to].
        cash_flows = await self._load_cash_flows(
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
        )

        # 6) Hand off to pure-function analytics.
        twr, twr_ann = compute_twr(nav_series, cash_flows)
        sharpe = compute_sharpe(daily_returns_from_navs(nav_series))
        navs_only = [s.total_value for s in nav_series]
        max_dd, max_dd_pct = compute_max_drawdown(navs_only)

        # 7) Period metadata for the response.
        if nav_series:
            period_days = (nav_series[-1].snapshot_date - nav_series[0].snapshot_date).days
        else:
            period_days = 0

        return AnalyticsResult(
            twr=twr,
            twr_annualized=twr_ann,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            period_days=period_days,
            snapshot_count=len(nav_series),
        )

    # ── internals ───────────────────────────────────────────────────────

    async def _resolve_date_from(
        self, period: Period, anchor: date, account_id: int | None
    ) -> date:
        if period == "1m":
            return anchor - timedelta(days=30)
        if period == "3m":
            return anchor - timedelta(days=90)
        if period == "6m":
            return anchor - timedelta(days=180)
        if period == "1y":
            return anchor - timedelta(days=365)
        if period == "ytd":
            return date(anchor.year, 1, 1)
        # "all" — earliest snapshot's date, else 1 day before today
        # (gives the empty / 1-day shape so downstream math degrades
        # to (0, 0) deterministically).
        earliest = await self._earliest_snapshot_date(account_id)
        return earliest or (anchor - timedelta(days=1))

    async def _earliest_snapshot_date(self, account_id: int | None) -> date | None:
        from sqlalchemy import asc

        from app.db.models.portfolio.snapshot import HoldingsSnapshot

        where = [HoldingsSnapshot.user_id == self._user.id]
        if account_id is None:
            where.append(HoldingsSnapshot.account_id.is_(None))
        else:
            where.append(HoldingsSnapshot.account_id == account_id)
        stmt = (
            select(HoldingsSnapshot.snapshot_date)
            .where(and_(*where))
            .order_by(asc(HoldingsSnapshot.snapshot_date))
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def _load_cash_flows(
        self,
        date_from: date,
        date_to: date,
        account_id: int | None,
    ) -> list[CashFlow]:
        """Translate `portfolio_trades` rows into CashFlow entries.

        BUY ↦ +amount (cash in); SELL ↦ -amount (cash out).
        DIVIDEND / SPLIT are ignored — see module docstring.
        """
        where = [
            PortfolioAccount.user_id == self._user.id,
            PortfolioTrade.trade_date >= date_from,
            PortfolioTrade.trade_date <= date_to,
        ]
        if account_id is not None:
            where.append(PortfolioTrade.account_id == account_id)

        stmt = (
            select(PortfolioTrade)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioTrade.account_id,
            )
            .where(and_(*where))
            .order_by(PortfolioTrade.trade_date.asc())
        )
        result = await self._db.execute(stmt)
        rows = list(result.scalars().all())

        flows: list[CashFlow] = []
        for t in rows:
            action = (t.action or "").upper()
            qty = t.quantity or _ZERO
            price = t.price or _ZERO
            fee = t.fee or _ZERO
            tax = t.tax or _ZERO
            if action == "BUY":
                amount = qty * price + fee + tax
                flows.append(CashFlow(flow_date=t.trade_date, amount=amount))
            elif action == "SELL":
                proceeds = qty * price - fee - tax
                # Negative because capital is leaving the portfolio.
                flows.append(CashFlow(flow_date=t.trade_date, amount=-proceeds))
            # DIVIDEND / SPLIT: skip — already reflected in NAV.
        return flows


__all__ = ["AnalyticsService", "Period"]
