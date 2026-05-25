"""CsvImportService — broker CSV → bulk trade insertion.

Round 10 Phase 4+: broker-aware parsing. The original Y2 Round 4
service had a single hand-coded CSV format; this version delegates to
a `BrokerParser` adapter (one per broker) registered in
`app.modules.portfolio.broker_parsers`. Auto-detect picks the right
adapter when the API caller doesn't specify a `broker_key`.

Atomicity model (unchanged from Y2)
-----------------------------------

We treat the whole batch as **one logical unit**:

1. parser pass — adapter parses every row, may emit per-row errors.
2. If any row failed AND ``dry_run=False`` → return the report with
   ``successful_rows=0`` and let the API layer roll back. NO DB writes
   leak (each `record_trade` call does its own `flush()`, but the API
   layer is the one that calls `commit()` — and it only commits when
   we report zero failures).
3. If every row passed, replay them through `PortfolioTradeService.
   record_trade` in chronological CSV order. Tier checks fire on every
   call; if the batch would blow the monthly quota, the very first row
   raises `TierLimitExceededError` BEFORE any partial write commits.

Backward-compatibility
~~~~~~~~~~~~~~~~~~~~~~

The legacy `_REQUIRED_HEADER` shape is still served by the
`GenericCsvParser` adapter, so the existing
`tests/integration/test_holdings_csv_import.py` continues to pass with
zero changes — the generic parser is the fallback when auto-detect
finds no broker-specific match.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING

from app.config import settings
from app.models.enums import Market
from app.modules.billing.tier_limits import get_limit
from app.modules.portfolio.broker_parsers import (
    BrokerParser,
    ParsedRow,
    build_default_parsers,
    detect_parser,
)
from app.modules.portfolio.broker_parsers.base import (
    ACTION_BUY,
    ACTION_SELL,
)
from app.schemas.holdings.import_csv import ImportResult, ImportResultRow
from app.services.portfolio.exceptions import (
    PortfolioInsufficientSharesError,
    PortfolioAccountNotFoundError,
    TierLimitExceededError,
)
from app.services.portfolio.trade_service import PortfolioTradeService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User


# Canonical action tokens accepted downstream. DIVIDEND / SPLIT rows
# are explicitly rejected at the service boundary — the dedicated
# /holdings/dividends endpoint owns dividend bookkeeping.
_ALLOWED_ACTIONS = {ACTION_BUY, ACTION_SELL}


class CsvImportService:
    """Parse a broker-style CSV and bulk-record trades.

    Lifecycle: one instance per HTTP request (mirrors
    `PortfolioTradeService`). State is the active session + user +
    parser registry.

    The service NEVER commits; the API layer owns the transaction so
    failures roll back the whole batch atomically.
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        parsers: dict[str, BrokerParser] | None = None,
    ) -> None:
        self._db = db
        self._user = user
        self._trade_service = PortfolioTradeService(db, user)
        # Default registry is process-shared (stateless parsers). Tests
        # inject custom registries to exercise edge cases.
        self._parsers: dict[str, BrokerParser] = (
            parsers if parsers is not None else build_default_parsers()
        )

    # ── public entrypoint ──────────────────────────────────────────────

    async def import_csv(
        self,
        account_id: int,
        csv_content: str,
        broker_key: str | None = None,
        dry_run: bool = False,
    ) -> ImportResult:
        """Parse, validate, then optionally record trades.

        Args:
            account_id: target portfolio account. Ownership verified
                via `PortfolioTradeService.record_trade`'s first step.
            csv_content: raw CSV text (UTF-8). Adapter-specific header
                requirements apply (see `app.modules.portfolio.
                broker_parsers`).
            broker_key: explicit adapter key (e.g. "interactive_brokers").
                When None we auto-detect via `BrokerParser.can_handle`.
            dry_run: when True, only parse + validate; no DB writes.

        Returns:
            ImportResult with per-row outcomes. When `dry_run=False`
            and any row failed, returns with ``successful_rows=0`` —
            the API layer rolls the session back without committing.

        Raises:
            ValueError: header missing / malformed / unknown broker_key
                → API maps to 422.
            PortfolioAccountNotFoundError: account missing/not owned → 404.
            TierLimitExceededError: monthly trades quota would be exceeded
                by the batch → 403. Pre-checked before any write.
        """
        parser = self._pick_parser(broker_key, csv_content)
        try:
            parsed_rows = parser.parse(csv_content)
        except ValueError:
            # Header / fatal-format issue. Re-raise so the endpoint
            # surfaces the standard `invalid_csv_format` 422.
            raise

        # Split rows into clean + errored. Per-row errors come from the
        # adapter (e.g. "invalid_action"); cross-cutting checks (action
        # in {BUY,SELL}, market enum, positive qty) happen here so a
        # buggy adapter can't sneak invalid data downstream.
        clean: list[ParsedRow] = []
        errors: list[ImportResultRow] = []
        for row in parsed_rows:
            error_code = self._cross_check(row)
            if error_code:
                errors.append(_row_to_result(row, error_code))
            elif row.error:
                errors.append(_row_to_result(row, row.error))
            else:
                clean.append(row)

        parsed_count = len(clean) + len(errors)
        failed_rows = len(errors)
        successful_rows = len(clean) if (failed_rows == 0 or dry_run) else 0

        if dry_run:
            return ImportResult(
                parsed_rows=parsed_count,
                successful_rows=len(clean),
                failed_rows=failed_rows,
                errors=errors,
                dry_run=True,
            )

        if failed_rows > 0:
            return ImportResult(
                parsed_rows=parsed_count,
                successful_rows=0,
                failed_rows=failed_rows,
                errors=errors,
                dry_run=False,
            )

        # Pre-flight tier check — see Y2 docstring for rationale.
        await self._assert_batch_fits_in_quota(len(clean))

        for r in clean:
            market = _coerce_market(r.market)
            await self._trade_service.record_trade(
                account_id=account_id,
                action=r.action,
                symbol=r.symbol,
                market=market,
                qty=r.quantity,
                price=r.price,
                fee=r.fee,
                tax=r.tax,
                trade_date=r.trade_date,
                note=r.note,
            )

        return ImportResult(
            parsed_rows=parsed_count,
            successful_rows=successful_rows,
            failed_rows=0,
            errors=[],
            dry_run=False,
        )

    # ── parser dispatch ────────────────────────────────────────────────

    def _pick_parser(self, broker_key: str | None, csv_content: str) -> BrokerParser:
        if broker_key:
            parser = self._parsers.get(broker_key)
            if parser is None:
                raise ValueError(f"unknown_broker_key:{broker_key}")
            return parser
        # Auto-detect — walk the registry, broker-specific first.
        for key, parser in self._parsers.items():
            if key == "generic":
                continue
            if parser.can_handle(csv_content):
                return parser
        # Fallback: generic parser (or detect_parser default if missing)
        return self._parsers.get("generic") or detect_parser(csv_content)

    # ── row validation (cross-cutting) ────────────────────────────────

    def _cross_check(self, row: ParsedRow) -> str | None:
        """Cross-cutting validators that apply to every parser's output."""
        if row.action not in _ALLOWED_ACTIONS:
            # Dividend / split tokens land here too — the parser flagged
            # them with `error="dividend_actions_not_supported"` already,
            # but generic / unknown actions still need this guard.
            if row.error is None:
                return "invalid_action"
            return None  # already errored by adapter
        if row.quantity <= Decimal("0"):
            return "invalid_quantity"
        if row.price <= Decimal("0"):
            return "invalid_price"
        if row.fee < Decimal("0"):
            return "invalid_fee"
        if row.tax < Decimal("0"):
            return "invalid_tax"
        if not row.symbol:
            return "missing_symbol"
        # Market validity is enforced inside `_coerce_market` at write
        # time; we surface it during cross-check too so dry-run shows
        # the error in the preview.
        if row.market is not None:
            try:
                Market(row.market)
            except ValueError:
                return "invalid_market"
        return None

    # ── tier guard (pre-flight, mirrors trade_service second line) ─────

    async def _assert_batch_fits_in_quota(self, batch_size: int) -> None:
        if not settings.enable_monetization:
            return
        limit = get_limit(self._user.tier, "max_trades_per_month")
        if limit is None:
            return
        current = await self._trade_service._trade_repo.count_by_user_this_month(self._user.id)
        if current + batch_size > limit:
            raise TierLimitExceededError(
                limit_key="max_trades_per_month",
                current=current,
                limit=limit,
            )

    # ── capability listing ────────────────────────────────────────────

    def list_brokers(self) -> list[dict[str, str]]:
        """Return the broker registry envelope used by GET /imports/brokers.

        Each entry: {broker_key, display_name}. Ordered as in the
        registry — broker-specific first, generic last — so the
        frontend dropdown shows real brokers above the fallback.
        """
        return [
            {"broker_key": key, "display_name": parser.DISPLAY_NAME}
            for key, parser in self._parsers.items()
        ]


# ── module-private helpers ────────────────────────────────────────────


def _coerce_market(raw: str | None) -> Market:
    """Convert a ParsedRow.market string into a Market enum.

    `None` defaults to US_NASDAQ because the bulk of adapters (IB,
    Schwab, Fidelity) leave market unset for US stocks. TW adapters
    (Yuanta, Fubon) always set TW_TWSE explicitly.

    Raises:
        ValueError: when `raw` is a non-empty string that doesn't
            match a Market enum value.
    """
    if not raw:
        return Market.US_NASDAQ
    return Market(raw)


def _row_to_result(row: ParsedRow, error: str) -> ImportResultRow:
    """Translate a ParsedRow + error code into the wire ImportResultRow."""
    return ImportResultRow(
        row_index=row.row_index,
        action=row.action or None,
        symbol=row.symbol or None,
        quantity=str(row.quantity) if row.quantity is not None else None,
        price=str(row.price) if row.price is not None else None,
        trade_date=row.trade_date.isoformat() if isinstance(row.trade_date, date_type) else None,
        error=error,
    )


__all__ = [
    "CsvImportService",
    "PortfolioInsufficientSharesError",
    "PortfolioAccountNotFoundError",
    "TierLimitExceededError",
]
