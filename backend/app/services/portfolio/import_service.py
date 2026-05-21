"""CsvImportService — broker CSV → bulk trade insertion.

Phase 4 extensibility hook called out in spec §11. The actual broker
API adapters (Yuanta / IB / etc.) will land later and feed the same
service through `import_rows(...)` once they are ready; the file in
front of you is just the "user uploads a CSV" entry point.

Atomicity model
---------------

We treat the whole batch as **one logical unit**:

1. dry-run pass — parse every row, collect per-row validation errors.
2. If any row failed AND ``dry_run=False`` → return the report with
   ``successful_rows=0`` and let the API layer roll back. NO DB writes
   leak (each `record_trade` call does its own `flush()`, but the API
   layer is the one that calls `commit()` — and it only commits when
   we report zero failures).
3. If every row passed, replay them through `PortfolioTradeService.
   record_trade` in chronological CSV order. Tier checks fire on every
   call; if the batch would blow the monthly quota, the very first row
   raises `TierLimitExceeded` BEFORE any partial write commits.

Why this works
~~~~~~~~~~~~~~

`AsyncSession` is auto-begin: every write goes through `flush()` and
sits in the transaction until either the API layer calls `commit()`
(happy path) or `rollback()` (failure). The trade service flushes but
never commits; commit lives one layer up. That makes "roll back the
whole batch" trivial — the API endpoint just chooses not to commit.

We additionally pre-validate every row in pure-python BEFORE issuing
any trade write, so the common failure case (typo, bad date, zero qty)
is reported without dirtying the session at all.
"""
from __future__ import annotations

import csv
import io
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import get_limit
from app.schemas.holdings.import_csv import ImportResult, ImportResultRow
from app.services.portfolio.exceptions import (
    InsufficientShares,
    PortfolioAccountNotFound,
    TierLimitExceeded,
)
from app.services.portfolio.trade_service import PortfolioTradeService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


# Canonical action tokens accepted by `PortfolioTradeService.record_trade`.
_BUY = "BUY"
_SELL = "SELL"
_ALLOWED_ACTIONS = {_BUY, _SELL}

# DIVIDEND / SPLIT rows are explicitly rejected from CSV import — the
# dedicated /holdings/dividends endpoint owns dividend bookkeeping (FIFO
# net_amount → realized_pnl) which we don't want a second code path to
# duplicate. Surface the row in `errors` so the user can fix the file
# rather than silently skipping (which would mislead the user about
# whether the broker CSV was fully ingested).
_DIVIDEND_ACTIONS = {"DIVIDEND", "DIV", "CASH_DIV", "STOCK_DIV", "SPLIT"}

_REQUIRED_HEADER = [
    "trade_date",
    "action",
    "symbol",
    "market",
    "quantity",
    "price",
    "fee",
    "tax",
    "note",
]


class CsvImportService:
    """Parse a broker-style CSV and bulk-record trades.

    Lifecycle: one instance per HTTP request (mirrors
    `PortfolioTradeService`). State is the active session + user.

    The service NEVER commits; the API layer owns the transaction so
    failures roll back the whole batch atomically.
    """

    def __init__(self, db: "AsyncSession", user: "User") -> None:
        self._db = db
        self._user = user
        self._trade_service = PortfolioTradeService(db, user)

    # ── public entrypoint ──────────────────────────────────────────────

    async def import_csv(
        self,
        account_id: int,
        csv_content: str,
        dry_run: bool = False,
    ) -> ImportResult:
        """Parse, validate, then optionally record trades.

        Args:
            account_id: target portfolio account. Ownership verified
                via `PortfolioTradeService.record_trade`'s first step.
            csv_content: raw CSV text (UTF-8).  Must include the
                canonical header row (see `_REQUIRED_HEADER`).
            dry_run: when True, only parse + validate; no DB writes.

        Returns:
            ImportResult with per-row outcomes. When `dry_run=False`
            and any row failed, returns with
            ``successful_rows=0`` — the API layer rolls the session
            back without committing.

        Raises:
            ValueError: header missing / malformed → API maps to 422.
            PortfolioAccountNotFound: account missing/not owned → 404.
            TierLimitExceeded: monthly trades quota would be exceeded
                by the batch → 403. Pre-checked before any write.
        """
        rows, errors, header_ok = self._parse(csv_content)
        if not header_ok:
            raise ValueError("invalid_csv_format: missing or malformed header")

        parsed_rows = len(rows) + len(errors)
        failed_rows = len(errors)
        # A successful row in dry-run is "validated"; in commit mode it
        # is "validated AND inserted". The number is the same because
        # we only commit when failed_rows == 0.
        successful_rows = len(rows) if (failed_rows == 0 or dry_run) else 0

        # On dry-run, return immediately with the validation report.
        # No session mutation happens here.
        if dry_run:
            return ImportResult(
                parsed_rows=parsed_rows,
                successful_rows=len(rows),
                failed_rows=failed_rows,
                errors=errors,
                dry_run=True,
            )

        # On commit and any row failed pre-validation → atomic rollback.
        # We do NOT issue any record_trade call; session stays clean.
        if failed_rows > 0:
            return ImportResult(
                parsed_rows=parsed_rows,
                successful_rows=0,
                failed_rows=failed_rows,
                errors=errors,
                dry_run=False,
            )

        # Pre-flight tier check: would the whole batch fit in the
        # remaining monthly quota? The trade service checks per-row,
        # but if row 1 succeeds and row 30 would exceed, row 1 has
        # already written. We pre-check up front so the user gets a
        # 403 BEFORE any partial write.
        await self._assert_batch_fits_in_quota(len(rows))

        # All rows valid + quota OK → write them in CSV order.
        # If any row raises a domain error mid-batch (e.g. SELL
        # exceeds the running lot total), we surface it as a 422 via
        # the endpoint's exception translator, and the endpoint
        # rolls back the entire session.
        for r in rows:
            await self._trade_service.record_trade(
                account_id=account_id,
                action=r["action"],
                symbol=r["symbol"],
                market=r["market"],
                qty=r["quantity"],
                price=r["price"],
                fee=r["fee"],
                tax=r["tax"],
                trade_date=r["trade_date"],
                note=r["note"],
            )

        return ImportResult(
            parsed_rows=parsed_rows,
            successful_rows=successful_rows,
            failed_rows=0,
            errors=[],
            dry_run=False,
        )

    # ── parsing helpers ────────────────────────────────────────────────

    def _parse(
        self, csv_content: str
    ) -> tuple[list[dict], list[ImportResultRow], bool]:
        """Validate header and split rows into (clean, errored).

        Returns:
            (parsed_rows, error_rows, header_ok). When the header is
            invalid, parsed_rows + error_rows are empty and the caller
            raises 422 immediately.
        """
        try:
            reader = csv.reader(io.StringIO(csv_content))
            header = next(reader, None)
        except csv.Error:
            return [], [], False

        if not header or [h.strip() for h in header] != _REQUIRED_HEADER:
            return [], [], False

        parsed: list[dict] = []
        errors: list[ImportResultRow] = []
        for idx, raw_row in enumerate(reader, start=2):
            # Skip wholly-empty rows so trailing newlines don't trip the
            # validation count. csv.reader emits [] for blank lines.
            if not raw_row or all(not (c or "").strip() for c in raw_row):
                continue
            outcome = self._validate_row(idx, raw_row)
            if isinstance(outcome, ImportResultRow):
                errors.append(outcome)
            else:
                parsed.append(outcome)
        return parsed, errors, True

    def _validate_row(
        self, row_index: int, raw: list[str]
    ) -> dict | ImportResultRow:
        """Return a parsed dict or an ImportResultRow with error set."""
        # Pad short rows so positional indexing below never IndexError's.
        cols = list(raw) + [""] * (len(_REQUIRED_HEADER) - len(raw))
        trade_date_s, action, symbol, market_s, qty_s, price_s, fee_s, tax_s, note = (
            cols[i].strip() for i in range(len(_REQUIRED_HEADER))
        )

        def err(code: str) -> ImportResultRow:
            return ImportResultRow(
                row_index=row_index,
                action=action or None,
                symbol=symbol or None,
                quantity=qty_s or None,
                price=price_s or None,
                trade_date=trade_date_s or None,
                error=code,
            )

        # Reject dividends explicitly so the file owner knows why.
        if action.upper() in _DIVIDEND_ACTIONS:
            return err("dividend_actions_not_supported")
        if action.upper() not in _ALLOWED_ACTIONS:
            return err("invalid_action")

        # Market enum match.
        try:
            market = Market(market_s)
        except ValueError:
            return err("invalid_market")

        # Decimal parse — InvalidOperation triggers for empty / garbage.
        try:
            qty = Decimal(qty_s)
        except InvalidOperation:
            return err("invalid_quantity")
        if qty <= Decimal("0"):
            return err("invalid_quantity")

        try:
            price = Decimal(price_s)
        except InvalidOperation:
            return err("invalid_price")
        if price <= Decimal("0"):
            return err("invalid_price")

        # fee / tax default to 0 when blank — broker CSVs often omit.
        try:
            fee = Decimal(fee_s) if fee_s else Decimal("0")
        except InvalidOperation:
            return err("invalid_fee")
        if fee < Decimal("0"):
            return err("invalid_fee")

        try:
            tax = Decimal(tax_s) if tax_s else Decimal("0")
        except InvalidOperation:
            return err("invalid_tax")
        if tax < Decimal("0"):
            return err("invalid_tax")

        # ISO date — fromisoformat raises ValueError on garbage.
        try:
            trade_date = date_type.fromisoformat(trade_date_s)
        except ValueError:
            return err("invalid_trade_date")

        if not symbol:
            return err("missing_symbol")

        return {
            "action": action.upper(),
            "symbol": symbol.upper(),
            "market": market,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "tax": tax,
            "trade_date": trade_date,
            "note": note or None,
        }

    # ── tier guard (pre-flight, mirrors trade_service second line) ─────

    async def _assert_batch_fits_in_quota(self, batch_size: int) -> None:
        """Refuse the whole batch when it would push the user over the
        monthly trades quota.

        The trade service does a per-row check too, but that would let
        the first N rows commit before the N+1th fails — and the API
        endpoint is the only place that issues commit. By pre-flighting
        here we keep the "all-or-nothing" guarantee even when an
        ill-tempered admin disables the dependency layer.
        """
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_trades_per_month")
        if limit is None:
            return
        # We reuse the trade_repo count helper attached to the inner
        # service so we don't have to construct another repo here.
        current = await self._trade_service._trade_repo.count_by_user_this_month(  # noqa: SLF001
            self._user.id
        )
        if current + batch_size > limit:
            raise TierLimitExceeded(
                limit_key="max_trades_per_month",
                current=current,
                limit=limit,
            )


# Re-exports we lean on from the API layer so the import path stays flat.
__all__ = [
    "CsvImportService",
    "InsufficientShares",
    "PortfolioAccountNotFound",
    "TierLimitExceeded",
]
