"""PortfolioTradeService — trade lifecycle + lot/position bookkeeping.

Most complex service in Phase 1. Orchestrates:

- `PortfolioAccountRepo`   ownership verification
- `PortfolioTradeRepo`     create / patch / delete trade rows
- `PortfolioLotRepo`       FIFO lot persistence
- `PortfolioPositionRepo`  materialized position upsert
- `cost_basis.apply_buy` / `apply_sell`  domain math (no DB)

Key invariants:

- Lot chain is **always derivable** from the immutable trade log.
  PATCH / DELETE of any trade triggers `_rebuild_position(account_id,
  symbol)` which replays every trade in chronological order — this is
  Q14.4's "全開放" choice (spec §13 AC6).
- Tier checks live here as the second line (spec §9). API layer also
  hooks the same checks via `tier_guard(...)` but a missing dependency
  must not let unbounded data through.
- All exceptions raised are domain-level
  (`app.services.portfolio.exceptions`). API layer translates them.
"""
from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import get_limit
from app.modules.portfolio.cost_basis import (
    CostBasisInputs,
    apply_buy,
    apply_sell,
    average_cost,
)
from app.modules.trade_journal.fifo_engine import (
    InsufficientSharesError,
    Lot,
)
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioLotRepo,
    PortfolioPositionRepo,
    PortfolioTradeRepo,
)
from app.services.audit import log_audit_event
from app.services.portfolio.exceptions import (
    InsufficientShares,
    PortfolioAccountNotFound,
    PortfolioTradeNotFound,
    TierLimitExceeded,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.trade import PortfolioTrade
    from app.models.user import User


# Canonical action strings on `portfolio_trades.action` (spec §6.2 Table 2).
# We accept these directly because there is no dedicated TradeType enum in
# `app.models.enums` and the schema column is `String(10)`.
_BUY = "BUY"
_SELL = "SELL"


class PortfolioTradeService:
    """Trade lifecycle service. Stateless — one instance per request."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._account_repo = PortfolioAccountRepo(db)
        self._trade_repo = PortfolioTradeRepo(db)
        self._lot_repo = PortfolioLotRepo(db)
        self._position_repo = PortfolioPositionRepo(db)

    # ── tier guards (spec §9 service-level second line) ─────────────────

    async def _assert_trades_quota(self) -> None:
        """Block when monthly trade quota for the tier is exhausted."""
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_trades_per_month")
        if limit is None:
            return
        current = await self._trade_repo.count_by_user_this_month(
            self._user.id
        )
        if current >= limit:
            raise TierLimitExceeded(
                limit_key="max_trades_per_month",
                current=current,
                limit=limit,
            )

    async def _assert_positions_quota_for_new_symbol(
        self, account_id: int, symbol: str, market: Market
    ) -> None:
        """When a BUY would open a brand-new (account, symbol, market)
        position, ensure the user is not at `max_positions` already.

        The repo's `count_by_user` counts position *rows* across the
        user's accounts, which is the spec §9 semantics for the
        quota.
        """
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_positions")
        if limit is None:
            return
        existing = await self._position_repo.get(
            account_id, symbol, market=market
        )
        if existing is not None and existing.quantity > Decimal("0"):
            # Adding to an already-tracked position; not a new row.
            return
        current = await self._position_repo.count_by_user(self._user.id)
        if current >= limit:
            raise TierLimitExceeded(
                limit_key="max_positions", current=current, limit=limit
            )

    # ── ownership helpers ──────────────────────────────────────────────

    async def _require_owned_account(self, account_id: int) -> None:
        account = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

    async def _require_owned_trade(self, trade_id: int) -> PortfolioTrade:
        trade = await self._trade_repo.get_by_id(
            trade_id, user_id=self._user.id
        )
        if trade is None:
            raise PortfolioTradeNotFound(
                f"trade {trade_id} not found or not owned"
            )
        return trade

    # ── public API ──────────────────────────────────────────────────────

    async def record_trade(
        self,
        account_id: int,
        action: str,
        symbol: str,
        market: Market,
        qty: Decimal,
        price: Decimal,
        fee: Decimal = Decimal("0"),
        tax: Decimal = Decimal("0"),
        trade_date: date_type | None = None,
        note: str | None = None,
    ) -> PortfolioTrade:
        """Record a BUY or SELL trade.

        Algorithm:
          1. Verify account ownership.
          2. Tier asserts: trades-per-month + (BUY only) positions count.
          3. INSERT the trade row.
          4. BUY:  apply_buy → INSERT lot → upsert position
                   (weighted avg_cost, qty incremented).
          5. SELL: load open lots → apply_sell → bulk-update lots →
                   upsert position (qty decremented, realized_pnl
                   accumulated).
          6. Audit log.

        Raises:
            PortfolioAccountNotFound, TierLimitExceeded, InsufficientShares,
            ValueError (on invalid action / non-positive qty).
        """
        if action not in (_BUY, _SELL):
            raise ValueError(
                f"unsupported action {action!r}; expected BUY or SELL"
            )
        if qty <= Decimal("0"):
            raise ValueError(f"qty must be positive, got {qty}")

        await self._require_owned_account(account_id)
        await self._assert_trades_quota()
        if action == _BUY:
            await self._assert_positions_quota_for_new_symbol(
                account_id, symbol, market
            )

        trade = await self._trade_repo.create(
            account_id=account_id,
            user_id=self._user.id,
            symbol=symbol,
            market=market,
            action=action,
            trade_date=trade_date or date_type.today(),
            price=price,
            quantity=qty,
            fee=fee,
            tax=tax,
            note=note,
        )
        # repo returns None only on wrong owner — already guarded above,
        # but keep a defensive branch.
        if trade is None:  # pragma: no cover
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

        if action == _BUY:
            await self._apply_buy_side(
                trade_id=trade.id,
                account_id=account_id,
                symbol=symbol,
                market=market,
                qty=qty,
                price=price,
                fee=fee,
            )
        else:
            await self._apply_sell_side(
                account_id=account_id,
                symbol=symbol,
                market=market,
                qty=qty,
                price=price,
                fee=fee,
                tax=tax,
            )

        await log_audit_event(
            self._db,
            action="portfolio_trade_added",
            user_id=self._user.id,
            resource_type="portfolio_trade",
            resource_id=str(trade.id),
            after_state={
                "account_id": account_id,
                "symbol": symbol,
                "market": market.value,
                "action": action,
                "qty": str(qty),
                "price": str(price),
            },
        )
        return trade

    async def update_trade(
        self, trade_id: int, **fields: Any
    ) -> PortfolioTrade:
        """PATCH a historical trade and replay the lot chain for that
        (account, symbol, market) tuple.

        Per Q14.4 全開放: any field on any trade may change. The cheapest
        correct strategy is a full rebuild — see `_rebuild_position`.
        """
        existing = await self._require_owned_trade(trade_id)
        before = {
            "symbol": existing.symbol,
            "market": existing.market.value if existing.market else None,
            "action": existing.action,
            "qty": str(existing.quantity) if existing.quantity is not None else None,
            "price": str(existing.price) if existing.price is not None else None,
        }
        # Snapshot the symbol/market BEFORE the patch — if the user
        # repointed a trade to a new symbol we need to rebuild BOTH old
        # and new positions.
        old_account_id = existing.account_id
        old_symbol = existing.symbol
        old_market = existing.market

        updated = await self._trade_repo.update(
            trade_id, user_id=self._user.id, **fields
        )
        if updated is None:  # pragma: no cover
            raise PortfolioTradeNotFound(
                f"trade {trade_id} not found or not owned"
            )

        # Wipe lots tied to this specific trade — they will be rebuilt
        # by the chronological replay.
        await self._lot_repo.delete_by_trade(trade_id)

        await self._rebuild_position(old_account_id, old_symbol, old_market)
        if (
            updated.symbol != old_symbol
            or updated.market != old_market
            or updated.account_id != old_account_id
        ):
            await self._rebuild_position(
                updated.account_id, updated.symbol, updated.market
            )

        await log_audit_event(
            self._db,
            action="portfolio_trade_updated",
            user_id=self._user.id,
            resource_type="portfolio_trade",
            resource_id=str(trade_id),
            before_state=before,
            after_state={
                "symbol": updated.symbol,
                "market": updated.market.value if updated.market else None,
                "action": updated.action,
                "qty": str(updated.quantity)
                if updated.quantity is not None
                else None,
                "price": str(updated.price)
                if updated.price is not None
                else None,
            },
        )
        return updated

    async def delete_trade(self, trade_id: int) -> None:
        """DELETE a historical trade and replay the lot chain.

        Cascade: FK ON DELETE CASCADE removes the trade's lots
        automatically; we still call `_rebuild_position` to reconstruct
        position quantity / avg_cost / realized_pnl from the remaining
        trades.
        """
        existing = await self._require_owned_trade(trade_id)
        account_id = existing.account_id
        symbol = existing.symbol
        market = existing.market

        deleted = await self._trade_repo.delete(
            trade_id, user_id=self._user.id
        )
        if not deleted:  # pragma: no cover
            raise PortfolioTradeNotFound(
                f"trade {trade_id} not found or not owned"
            )
        # Lots are cascaded by FK on portfolio_trades.id, but to be
        # safe against any future change to the FK we explicitly wipe
        # by trade_id too (idempotent).
        await self._lot_repo.delete_by_trade(trade_id)

        await self._rebuild_position(account_id, symbol, market)

        await log_audit_event(
            self._db,
            action="portfolio_trade_deleted",
            user_id=self._user.id,
            resource_type="portfolio_trade",
            resource_id=str(trade_id),
            before_state={
                "account_id": account_id,
                "symbol": symbol,
                "market": market.value if market else None,
                "action": existing.action,
                "qty": str(existing.quantity)
                if existing.quantity is not None
                else None,
                "price": str(existing.price)
                if existing.price is not None
                else None,
            },
        )

    # ── private helpers ────────────────────────────────────────────────

    async def _apply_buy_side(
        self,
        trade_id: int,
        account_id: int,
        symbol: str,
        market: Market,
        qty: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> None:
        """Insert a new lot for the BUY, then re-derive the position
        roll-up from ALL open lots (so weighted avg_cost stays exact).
        """
        # 1. Compute the BUY lot's cost_per_unit (delegated to domain).
        buy = apply_buy(lot_id=trade_id, qty=qty, price=price, fee=fee)
        # 2. Persist the lot. Tie it to the originating trade.
        await self._lot_repo.create(
            trade_id=trade_id,
            account_id=account_id,
            symbol=symbol,
            market=market,
            original_qty=buy.new_lot.original_qty,
            remaining_qty=buy.new_lot.remaining_qty,
            cost_per_unit=buy.new_lot.cost_per_unit,
        )
        # 3. Re-derive position from open lots (single source of truth).
        await self._reupsert_position_from_open_lots(
            account_id=account_id, symbol=symbol, market=market
        )

    async def _apply_sell_side(
        self,
        account_id: int,
        symbol: str,
        market: Market,
        qty: Decimal,
        price: Decimal,
        fee: Decimal,
        tax: Decimal,
    ) -> None:
        """Consume oldest open lots FIFO, persist remaining_qty updates,
        accumulate realized_pnl on the position row.
        """
        open_lots_orm = await self._lot_repo.list_open_for_position(
            account_id=account_id, symbol=symbol, market=market
        )
        domain_lots = [_orm_lot_to_domain(row) for row in open_lots_orm]
        try:
            sell = apply_sell(
                CostBasisInputs(
                    open_lots=domain_lots,
                    sell_qty=qty,
                    sell_price=price,
                    sell_fee=fee,
                    sell_tax=tax,
                )
            )
        except InsufficientSharesError as exc:
            raise InsufficientShares(str(exc)) from exc

        # Persist lot consumption in one bulk UPDATE.
        bulk: list[tuple[int, Decimal, bool]] = [
            (lot.lot_id, lot.remaining_qty, lot.is_exhausted)
            for lot in sell.updated_lots
        ]
        await self._lot_repo.bulk_update(bulk)

        # Update the position row: subtract qty, accumulate realized_pnl.
        await self._reupsert_position_from_open_lots(
            account_id=account_id,
            symbol=symbol,
            market=market,
            realized_pnl_delta=sell.realized_pnl,
        )

    async def _reupsert_position_from_open_lots(
        self,
        account_id: int,
        symbol: str,
        market: Market,
        realized_pnl_delta: Decimal = Decimal("0"),
    ) -> None:
        """Recompute (qty, avg_cost, total_cost, is_closed) from the
        live open lots and upsert.

        `realized_pnl_delta` is added to whatever realized total the
        position row already holds (None / missing rows treated as 0).
        For rebuilds (PATCH / DELETE), pass 0 and accumulate via the
        replay loop in `_rebuild_position`.
        """
        open_lots = await self._lot_repo.list_open_for_position(
            account_id=account_id, symbol=symbol, market=market
        )
        domain_lots = [_orm_lot_to_domain(row) for row in open_lots]
        total_qty = sum(
            (lot.remaining_qty for lot in domain_lots), Decimal("0")
        )
        avg = average_cost(domain_lots)
        total_cost = avg * total_qty if total_qty > Decimal("0") else Decimal("0")
        is_closed = total_qty == Decimal("0")

        existing = await self._position_repo.get(
            account_id, symbol, market=market
        )
        prior_realized = (
            existing.realized_pnl
            if existing is not None and existing.realized_pnl is not None
            else Decimal("0")
        )
        currency = (
            existing.currency if existing is not None else _currency_for(market)
        )

        await self._position_repo.upsert(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=currency,
            quantity=total_qty,
            avg_cost=avg if total_qty > Decimal("0") else None,
            total_cost=total_cost if total_qty > Decimal("0") else None,
            realized_pnl=prior_realized + realized_pnl_delta,
            is_closed=is_closed,
        )

    async def _rebuild_position(
        self, account_id: int, symbol: str, market: Market
    ) -> None:
        """Replay every BUY/SELL for (account_id, symbol, market) in
        chronological order and reconstruct lots + position from scratch.

        Algorithm:
          1. List all trades for the (account, symbol, market) tuple,
             ordered by `trade_date ASC, id ASC` (paginate in case of
             >50 trades — Phase 1 cap is 500/month so the upper bound
             is bounded).
          2. Wipe every lot tied to those trade ids.
          3. Walk the trades chronologically:
             * BUY  -> apply_buy, append the resulting lot to an
                       in-memory list, INSERT into DB tied to that
                       trade's id.
             * SELL -> apply_sell against the in-memory list (which
                       mirrors DB lot order), bulk-update the touched
                       DB lots, accumulate realized_pnl.
          4. Upsert the position with the final aggregate.

        Edge cases:
          - Zero trades after delete  → position qty=0, is_closed=True,
                                        realized_pnl=0.
          - Trade with non-BUY/SELL  → ignored at replay (dividends /
                                       splits handled in Phase 3).
          - Same-day BUY+SELL        → ordered by `id` after `trade_date`
                                       so newer rows always replay last
                                       (consistent with FIFO insertion).
        """
        trades = await self._list_all_trades_for_position(
            account_id, symbol, market
        )
        # Wipe ALL lots for these trades — clean slate replay.
        for t in trades:
            await self._lot_repo.delete_by_trade(t.id)

        in_memory_lots: list[Lot] = []
        accumulated_realized = Decimal("0")

        for t in trades:
            if t.action == _BUY:
                qty = t.quantity or Decimal("0")
                price = t.price or Decimal("0")
                fee = t.fee or Decimal("0")
                if qty <= Decimal("0"):
                    continue
                buy = apply_buy(
                    lot_id=t.id, qty=qty, price=price, fee=fee
                )
                # Persist the new lot tied to this trade.
                await self._lot_repo.create(
                    trade_id=t.id,
                    account_id=account_id,
                    symbol=symbol,
                    market=market,
                    original_qty=buy.new_lot.original_qty,
                    remaining_qty=buy.new_lot.remaining_qty,
                    cost_per_unit=buy.new_lot.cost_per_unit,
                )
                in_memory_lots.append(buy.new_lot)
            elif t.action == _SELL:
                qty = t.quantity or Decimal("0")
                price = t.price or Decimal("0")
                fee = t.fee or Decimal("0")
                tax = t.tax or Decimal("0")
                if qty <= Decimal("0"):
                    continue
                try:
                    sell = apply_sell(
                        CostBasisInputs(
                            open_lots=in_memory_lots,
                            sell_qty=qty,
                            sell_price=price,
                            sell_fee=fee,
                            sell_tax=tax,
                        )
                    )
                except InsufficientSharesError as exc:
                    # Replay invariant violated: this means the user
                    # PATCHed history into an impossible state. Surface
                    # as domain error so the API layer can 422 back.
                    raise InsufficientShares(
                        f"rebuild replay: {exc}"
                    ) from exc
                accumulated_realized += sell.realized_pnl
                # Mutate in_memory_lots in place to match what
                # apply_sell returned.
                in_memory_lots = sell.updated_lots
                # Persist remaining_qty updates for affected DB lots.
                bulk: list[tuple[int, Decimal, bool]] = [
                    (lot.lot_id, lot.remaining_qty, lot.is_exhausted)
                    for lot in sell.updated_lots
                ]
                await self._lot_repo.bulk_update(bulk)
            # other actions (DIVIDEND / SPLIT) ignored in Phase 1

        # Final position aggregate.
        total_qty = sum(
            (lot.remaining_qty for lot in in_memory_lots), Decimal("0")
        )
        avg = average_cost(in_memory_lots)
        existing = await self._position_repo.get(
            account_id, symbol, market=market
        )
        currency = (
            existing.currency if existing is not None else _currency_for(market)
        )
        await self._position_repo.upsert(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=currency,
            quantity=total_qty,
            avg_cost=avg if total_qty > Decimal("0") else None,
            total_cost=avg * total_qty if total_qty > Decimal("0") else None,
            realized_pnl=accumulated_realized,
            is_closed=total_qty == Decimal("0"),
        )

    async def _list_all_trades_for_position(
        self, account_id: int, symbol: str, market: Market
    ) -> list[PortfolioTrade]:
        """Fetch every trade for (account, symbol, market), sorted ASC
        by (trade_date, id). Uses repo.list_by_account + Python-side
        filter to honor the §11 R2 no-raw-SQL rule.

        The repo orders DESC, so we reverse and filter here.
        """
        # `count_by_user_this_month` is not the same query; we need all
        # trades, not just this month. List_by_account paginates — we
        # pull large pages until empty.
        all_rows: list[PortfolioTrade] = []
        page_size = 500
        offset = 0
        while True:
            page = await self._trade_repo.list_by_account(
                account_id=account_id,
                user_id=self._user.id,
                limit=page_size,
                offset=offset,
            )
            if not page:
                break
            all_rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        # Filter to the target (symbol, market), sort ASC by (date, id).
        filtered = [
            r for r in all_rows if r.symbol == symbol and r.market == market
        ]
        filtered.sort(key=lambda r: (r.trade_date, r.id))
        return filtered


# ── module-private helpers (pure functions) ────────────────────────────


def _orm_lot_to_domain(row: Any) -> Lot:
    """Translate a PortfolioLot ORM row into a domain Lot dataclass.

    We keep the domain layer ignorant of SQLAlchemy by translating
    here, NOT in the domain module (spec §11 R1)."""
    return Lot(
        lot_id=row.id,
        original_qty=row.original_qty,
        remaining_qty=row.remaining_qty,
        cost_per_unit=row.cost_per_unit,
        is_exhausted=row.is_exhausted,
    )


def _currency_for(market: Market) -> str:
    """Default currency for a market — used when upserting a position
    with no prior row to inherit currency from. TW markets -> TWD,
    US markets -> USD."""
    if market in (Market.US_NYSE, Market.US_NASDAQ):
        return "USD"
    return "TWD"
