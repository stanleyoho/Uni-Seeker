"""PortfolioDividendService — dividend recording + cost-basis effects.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §5.2.

Orchestrates:

- `PortfolioAccountRepo`    ownership verification
- `PortfolioDividendRepo`   create / patch / delete dividend rows
- `PortfolioLotRepo`        STOCK dividend lot scaling (preserves total cost)
- `PortfolioPositionRepo`   CASH dividend realized_pnl accrual + STOCK
                            dividend quantity / avg_cost re-derivation
- `dividend_processor.*`    pure-Python math (no DB, no FastAPI)

Tier enforcement (spec §9 双保险):
- Endpoint guard (`tier_guard(feature="dividends")`) is the first line.
- This service is the second line — `has_feature(tier, "dividends")` is
  asserted at the top of every `record_dividend` / mutation; FREE tier
  raises `TierFeatureUnavailable` even if the API guard is bypassed.

Phase 2 MVP simplifications (documented for follow-up):
- `update_dividend` only allows `note` / `pay_date` / `withholding_tax`.
  Amount / quantity / ratio changes require delete + recreate to avoid
  cost-basis replay complexity (Phase 4 territory).
- `delete_dividend` performs a simple delete: cost-basis effects from
  the original record are NOT reversed. The user is responsible for
  manual cleanup of `realized_pnl` / `lots` if needed. The opposite
  policy (full reversal) is tracked under Phase 3+ corporate-action
  processor work.

Transaction boundary: every public method completes ALL writes
(dividend row + lot updates + position upsert + audit log) before
returning. Caller (API layer) commits or rolls back. A partial failure
within a single call leaves the session in a state the caller will
choose to roll back — see `PortfolioTradeService` for the same pattern.
"""
from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.cost_basis import average_cost
from app.modules.portfolio.dividend_processor import (
    CashDividendInputs,
    StockDividendInputs,
    process_cash_dividend,
    process_stock_dividend,
)
from app.modules.trade_journal.fifo_engine import Lot
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioDividendRepo,
    PortfolioLotRepo,
    PortfolioPositionRepo,
)
from app.services.audit import log_audit_event
from app.services.portfolio.exceptions import (
    PortfolioAccountNotFound,
    PortfolioServiceError,
    TierFeatureUnavailable,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.dividend import PortfolioDividend
    from app.models.user import User


_CASH = "CASH"
_STOCK = "STOCK"
_VALID_DIVIDEND_TYPES = frozenset({_CASH, _STOCK})

# Fields callers may mutate via `update_dividend`. Anything else is
# considered immutable in Phase 2 MVP (see module docstring).
_UPDATABLE_FIELDS = frozenset({"note", "pay_date", "withholding_tax"})


class PortfolioDividendNotFound(PortfolioServiceError):
    """Dividend id does not exist OR its parent account is not owned by
    the requesting user — same 404/403 collapse as trade lookups."""


class PortfolioDividendService:
    """Dividend lifecycle service. Stateless — one instance per request."""

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._account_repo = PortfolioAccountRepo(db)
        self._dividend_repo = PortfolioDividendRepo(db)
        self._lot_repo = PortfolioLotRepo(db)
        self._position_repo = PortfolioPositionRepo(db)

    # ── tier / ownership guards ────────────────────────────────────────

    def _assert_dividends_feature(self) -> None:
        """Block when the user's tier lacks the `dividends` feature flag.

        Bypassed when `enable_monetization=False` (dev/test parity with
        `tier_limits.tier_guard`).
        """
        if not settings.enable_monetization:
            return
        if not has_feature(self._user.tier, "dividends"):
            raise TierFeatureUnavailable(feature="dividends")

    async def _require_owned_account(self, account_id: int) -> None:
        account = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if account is None:
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

    async def _require_owned_dividend(
        self, dividend_id: int
    ) -> PortfolioDividend:
        row = await self._dividend_repo.get_by_id(
            dividend_id, user_id=self._user.id
        )
        if row is None:
            raise PortfolioDividendNotFound(
                f"dividend {dividend_id} not found or not owned"
            )
        return row

    # ── public API ─────────────────────────────────────────────────────

    async def record_dividend(
        self,
        *,
        account_id: int,
        symbol: str,
        market: Market,
        dividend_type: str,
        ex_dividend_date: date_type,
        pay_date: date_type | None = None,
        amount_per_share: Decimal | None = None,
        quantity_at_record: Decimal,
        ratio: Decimal | None = None,
        currency: str = "TWD",
        withholding_tax: Decimal = Decimal("0"),
        note: str | None = None,
    ) -> PortfolioDividend:
        """Record a CASH or STOCK dividend event.

        Behaviour split:
        - **CASH**: `amount_per_share` required; cost basis untouched;
          `net_amount` is added to `positions.realized_pnl` (spec §7.2 —
          confirms the `dividend_processor` flag: realized_pnl_delta =
          net_amount). The dividend row stores the gross
          `amount_per_share`, `quantity_at_record`, and `withholding_tax`
          verbatim — the gross / net totals are re-derived in the service /
          schema layer to keep SQLite/Postgres parity (model docstring).
        - **STOCK**: `ratio` required (> 0); every open lot for
          (account, symbol, market) is scaled by `(1 + ratio)`, preserving
          per-lot total cost; position is re-upserted from the scaled lots
          (new quantity, new weighted avg_cost). The dividend row stores
          `ratio` in `amount_per_share` (CHECK > 0 is satisfied because
          ratios are positive) plus a human-readable `note` like
          ``"STOCK dividend ratio=0.10"`` for forensic clarity.

        Raises:
            ValueError: invalid `dividend_type`, missing required field
                for the chosen type, or non-positive `quantity_at_record`.
            PortfolioAccountNotFound: account missing or not owned.
            TierFeatureUnavailable: tier lacks `dividends` feature.
        """
        # Input validation -------------------------------------------------
        if dividend_type not in _VALID_DIVIDEND_TYPES:
            raise ValueError(
                f"unsupported dividend_type {dividend_type!r}; "
                f"expected one of {sorted(_VALID_DIVIDEND_TYPES)}"
            )
        if quantity_at_record <= Decimal("0"):
            raise ValueError(
                f"quantity_at_record must be positive, got {quantity_at_record}"
            )
        if dividend_type == _CASH:
            if amount_per_share is None or amount_per_share <= Decimal("0"):
                raise ValueError(
                    "amount_per_share required and > 0 for CASH dividend"
                )
        else:  # STOCK
            if ratio is None or ratio <= Decimal("0"):
                raise ValueError(
                    "ratio required and > 0 for STOCK dividend"
                )

        # Guards -----------------------------------------------------------
        self._assert_dividends_feature()
        await self._require_owned_account(account_id)

        if dividend_type == _CASH:
            return await self._record_cash(
                account_id=account_id,
                symbol=symbol,
                market=market,
                ex_dividend_date=ex_dividend_date,
                pay_date=pay_date,
                amount_per_share=amount_per_share,  # type: ignore[arg-type]
                quantity_at_record=quantity_at_record,
                currency=currency,
                withholding_tax=withholding_tax,
                note=note,
            )
        return await self._record_stock(
            account_id=account_id,
            symbol=symbol,
            market=market,
            ex_dividend_date=ex_dividend_date,
            pay_date=pay_date,
            ratio=ratio,  # type: ignore[arg-type]
            quantity_at_record=quantity_at_record,
            currency=currency,
            note=note,
        )

    async def list_dividends(
        self, account_id: int | None = None
    ) -> list[PortfolioDividend]:
        """List dividends scoped to the user.

        When `account_id` is given, the account is verified to belong to
        the user first (cross-user / unknown account → empty list, not
        an exception). When omitted, returns every dividend across all
        of the user's accounts, ex_dividend_date DESC.
        """
        if account_id is None:
            return await self._dividend_repo.list_by_user(self._user.id)
        owned = await self._account_repo.get_by_id(
            account_id, user_id=self._user.id
        )
        if owned is None:
            return []
        return await self._dividend_repo.list_by_account(
            account_id=account_id, user_id=self._user.id
        )

    async def get_dividend(self, dividend_id: int) -> PortfolioDividend:
        """Fetch one owned dividend or raise `PortfolioDividendNotFound`."""
        return await self._require_owned_dividend(dividend_id)

    async def update_dividend(
        self, dividend_id: int, **fields: Any
    ) -> PortfolioDividend:
        """PATCH a dividend; only `note` / `pay_date` / `withholding_tax`
        may change. Any other key surfaced via `fields` raises
        `ValueError` so the API layer can return 422.

        Amount / quantity / ratio / type / symbol changes are forbidden
        in Phase 2 MVP — they would require a full cost-basis replay
        which we do not implement here. Workaround: delete + recreate.
        """
        self._assert_dividends_feature()
        existing = await self._require_owned_dividend(dividend_id)

        # Reject any immutable key the caller tried to slip through.
        bad_keys = [k for k in fields if k not in _UPDATABLE_FIELDS]
        if bad_keys:
            raise ValueError(
                f"immutable dividend fields cannot be patched: {sorted(bad_keys)}; "
                f"updatable fields are {sorted(_UPDATABLE_FIELDS)}. "
                "Delete and recreate the dividend to change the others."
            )

        before = {
            "note": existing.note,
            "pay_date": existing.pay_date.isoformat() if existing.pay_date else None,
            "withholding_tax": str(existing.withholding_tax),
        }
        updated = await self._dividend_repo.update(
            dividend_id, user_id=self._user.id, **fields
        )
        if updated is None:  # pragma: no cover — race with delete
            raise PortfolioDividendNotFound(
                f"dividend {dividend_id} not found or not owned"
            )
        await log_audit_event(
            self._db,
            action="portfolio_dividend_updated",
            user_id=self._user.id,
            resource_type="portfolio_dividend",
            resource_id=str(dividend_id),
            before_state=before,
            after_state={
                "note": updated.note,
                "pay_date": updated.pay_date.isoformat()
                if updated.pay_date
                else None,
                "withholding_tax": str(updated.withholding_tax),
            },
        )
        return updated

    async def delete_dividend(self, dividend_id: int) -> None:
        """DELETE a dividend row (simple delete — cost basis NOT reversed,
        see module docstring for rationale).
        """
        self._assert_dividends_feature()
        existing = await self._require_owned_dividend(dividend_id)
        before = {
            "account_id": existing.account_id,
            "symbol": existing.symbol,
            "market": existing.market.value if existing.market else None,
            "dividend_type": existing.dividend_type,
            "ex_dividend_date": existing.ex_dividend_date.isoformat(),
        }
        deleted = await self._dividend_repo.delete(
            dividend_id, user_id=self._user.id
        )
        if not deleted:  # pragma: no cover
            raise PortfolioDividendNotFound(
                f"dividend {dividend_id} not found or not owned"
            )
        await log_audit_event(
            self._db,
            action="portfolio_dividend_deleted",
            user_id=self._user.id,
            resource_type="portfolio_dividend",
            resource_id=str(dividend_id),
            before_state=before,
        )

    # ── private orchestration helpers ──────────────────────────────────

    async def _record_cash(
        self,
        *,
        account_id: int,
        symbol: str,
        market: Market,
        ex_dividend_date: date_type,
        pay_date: date_type | None,
        amount_per_share: Decimal,
        quantity_at_record: Decimal,
        currency: str,
        withholding_tax: Decimal,
        note: str | None,
    ) -> PortfolioDividend:
        """CASH dividend: pure cash income.

        Order of operations (matters for partial-failure safety):
          1. Domain math (pure, can raise ValueError before any DB write).
          2. INSERT dividend row.
          3. Accumulate `net_amount` into `positions.realized_pnl` for the
             matching (account_id, symbol, market) row. If no position row
             exists yet (edge case — user records a dividend without
             having recorded the BUY through us), we upsert a zero-qty
             position carrying just the realized P&L.
          4. Audit log.
        """
        result = process_cash_dividend(
            CashDividendInputs(
                qty_at_record=quantity_at_record,
                amount_per_share=amount_per_share,
                withholding_tax=withholding_tax,
            )
        )

        dividend = await self._dividend_repo.create(
            account_id=account_id,
            user_id=self._user.id,
            symbol=symbol,
            market=market,
            dividend_type=_CASH,
            ex_dividend_date=ex_dividend_date,
            pay_date=pay_date,
            amount_per_share=amount_per_share,
            quantity_at_record=quantity_at_record,
            currency=currency,
            withholding_tax=withholding_tax,
            note=note,
        )
        if dividend is None:  # pragma: no cover — guarded above
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

        await self._accrue_realized_pnl(
            account_id=account_id,
            symbol=symbol,
            market=market,
            delta=result.realized_pnl_delta,
            currency=currency,
        )

        await log_audit_event(
            self._db,
            action="portfolio_dividend_recorded",
            user_id=self._user.id,
            resource_type="portfolio_dividend",
            resource_id=str(dividend.id),
            after_state={
                "account_id": account_id,
                "symbol": symbol,
                "market": market.value,
                "dividend_type": _CASH,
                "amount_per_share": str(amount_per_share),
                "quantity_at_record": str(quantity_at_record),
                "net_amount": str(result.net_amount),
                "withholding_tax": str(withholding_tax),
            },
        )
        return dividend

    async def _record_stock(
        self,
        *,
        account_id: int,
        symbol: str,
        market: Market,
        ex_dividend_date: date_type,
        pay_date: date_type | None,
        ratio: Decimal,
        quantity_at_record: Decimal,
        currency: str,
        note: str | None,
    ) -> PortfolioDividend:
        """STOCK dividend (配股): scale every open lot by (1 + ratio).

        Order of operations:
          1. Load open lots for (account_id, symbol, market).
          2. Domain math (preserves total cost per lot).
          3. Persist lot updates via bulk_update: new remaining_qty,
             new cost_per_unit. We also need original_qty to scale —
             the schema does not let `bulk_update` carry it, so we
             issue per-lot updates for the cost+original scaled fields
             via a fresh `update_remaining` loop. STOCK dividends are
             rare (a handful per year per holding) so the N-round trip
             cost is negligible compared to BUY-heavy trade rebuilds.
          4. INSERT dividend row (ratio stored in amount_per_share, full
             ratio also recorded in note for human readability).
          5. Re-derive position quantity / avg_cost from the now-scaled
             lots; realized_pnl is left untouched.
          6. Audit log.
        """
        open_lots_orm = await self._lot_repo.list_open_for_position(
            account_id=account_id, symbol=symbol, market=market
        )
        domain_lots = [
            Lot(
                lot_id=row.id,
                original_qty=row.original_qty,
                remaining_qty=row.remaining_qty,
                cost_per_unit=row.cost_per_unit,
                is_exhausted=row.is_exhausted,
            )
            for row in open_lots_orm
        ]
        stock_result = process_stock_dividend(
            StockDividendInputs(ratio=ratio, open_lots=domain_lots)
        )

        # Persist lot scaling. We need to set original_qty + remaining_qty
        # + cost_per_unit per lot; lot_repo.bulk_update only covers
        # remaining_qty + is_exhausted, so we hand-roll the per-row update.
        # Each row is a single UPDATE; STOCK dividends touch <50 lots in
        # practice (Phase 2 cap is `max_positions=50` for BASIC tier).
        from sqlalchemy import update as sa_update

        from app.db.models.portfolio.lot import PortfolioLot

        for updated_lot in stock_result.updated_lots:
            await self._db.execute(
                sa_update(PortfolioLot)
                .where(PortfolioLot.id == updated_lot.lot_id)
                .values(
                    original_qty=updated_lot.original_qty,
                    remaining_qty=updated_lot.remaining_qty,
                    cost_per_unit=updated_lot.cost_per_unit,
                    is_exhausted=updated_lot.is_exhausted,
                )
            )
        await self._db.flush()

        # Build the dividend row's note. Preserve caller's note if any.
        ratio_note = f"STOCK dividend ratio={ratio}"
        full_note = (
            f"{note} | {ratio_note}" if note else ratio_note
        )

        dividend = await self._dividend_repo.create(
            account_id=account_id,
            user_id=self._user.id,
            symbol=symbol,
            market=market,
            dividend_type=_STOCK,
            ex_dividend_date=ex_dividend_date,
            pay_date=pay_date,
            # CHECK constraint requires amount_per_share > 0; ratio is
            # validated > 0 above, so reusing the column is safe and
            # avoids a schema migration for Phase 2.
            amount_per_share=ratio,
            quantity_at_record=quantity_at_record,
            currency=currency,
            withholding_tax=Decimal("0"),
            note=full_note,
        )
        if dividend is None:  # pragma: no cover — guarded above
            raise PortfolioAccountNotFound(
                f"account {account_id} not found or not owned"
            )

        # Re-derive position from scaled lots.
        await self._reupsert_position_from_lots(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=currency,
        )

        await log_audit_event(
            self._db,
            action="portfolio_dividend_recorded",
            user_id=self._user.id,
            resource_type="portfolio_dividend",
            resource_id=str(dividend.id),
            after_state={
                "account_id": account_id,
                "symbol": symbol,
                "market": market.value,
                "dividend_type": _STOCK,
                "ratio": str(ratio),
                "quantity_at_record": str(quantity_at_record),
                "total_new_qty_added": str(stock_result.total_new_qty_added),
            },
        )
        return dividend

    async def _accrue_realized_pnl(
        self,
        *,
        account_id: int,
        symbol: str,
        market: Market,
        delta: Decimal,
        currency: str,
    ) -> None:
        """Add `delta` to the position row's realized_pnl. If no row exists
        (user records a dividend without any prior BUY for the symbol),
        we still upsert a zero-qty row carrying the cash income so the
        portfolio summary correctly reflects realized cash.
        """
        existing = await self._position_repo.get(
            account_id, symbol, market=market
        )
        prior_realized = (
            existing.realized_pnl
            if existing is not None and existing.realized_pnl is not None
            else Decimal("0")
        )
        if existing is None:
            await self._position_repo.upsert(
                account_id=account_id,
                symbol=symbol,
                market=market,
                currency=currency,
                quantity=Decimal("0"),
                avg_cost=None,
                total_cost=None,
                realized_pnl=prior_realized + delta,
                is_closed=True,
            )
            return
        await self._position_repo.upsert(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=existing.currency,
            quantity=existing.quantity,
            avg_cost=existing.avg_cost_fifo,
            total_cost=existing.total_cost,
            realized_pnl=prior_realized + delta,
            is_closed=existing.is_closed,
        )

    async def _reupsert_position_from_lots(
        self,
        *,
        account_id: int,
        symbol: str,
        market: Market,
        currency: str,
    ) -> None:
        """Recompute quantity + weighted avg_cost from the currently
        persisted open lots; preserves realized_pnl + currency on the
        existing row (or falls back to the provided `currency` when
        upserting fresh).
        """
        open_lots_orm = await self._lot_repo.list_open_for_position(
            account_id=account_id, symbol=symbol, market=market
        )
        domain_lots = [
            Lot(
                lot_id=row.id,
                original_qty=row.original_qty,
                remaining_qty=row.remaining_qty,
                cost_per_unit=row.cost_per_unit,
                is_exhausted=row.is_exhausted,
            )
            for row in open_lots_orm
        ]
        total_qty = sum(
            (lot.remaining_qty for lot in domain_lots), Decimal("0")
        )
        avg = average_cost(domain_lots)
        total_cost = (
            avg * total_qty if total_qty > Decimal("0") else Decimal("0")
        )
        existing = await self._position_repo.get(
            account_id, symbol, market=market
        )
        prior_realized = (
            existing.realized_pnl
            if existing is not None and existing.realized_pnl is not None
            else Decimal("0")
        )
        row_currency = existing.currency if existing is not None else currency
        await self._position_repo.upsert(
            account_id=account_id,
            symbol=symbol,
            market=market,
            currency=row_currency,
            quantity=total_qty,
            avg_cost=avg if total_qty > Decimal("0") else None,
            total_cost=total_cost if total_qty > Decimal("0") else None,
            realized_pnl=prior_realized,
            is_closed=total_qty == Decimal("0"),
        )


__all__ = [
    "PortfolioDividendService",
    "PortfolioDividendNotFound",
]
