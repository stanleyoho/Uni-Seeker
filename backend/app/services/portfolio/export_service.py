"""CsvExportService — Phase 4 tax-export hook (spec §11 extensibility).

Produces UTF-8 CSV bytes for trades / positions / dividends / summary so
the user can drop the file into tax software or external analysis.

Tier gate
---------
``tax_export`` feature flag in ``config/tier_limits.yaml`` — currently
``free=false, basic=false, pro=true``. The check runs at the top of
every public ``export_*`` method so the service is callable directly
from CLI / batch jobs without an HTTP guard. ``enable_monetization=False``
(dev/test) bypasses the check, mirroring every other portfolio service.

Output contract
---------------
- UTF-8 encoded with a leading BOM (``\\ufeff``) so Excel autodetects
  the encoding and renders Chinese ``note`` fields correctly.
- ``csv.writer`` handles quoting per RFC 4180 (default
  ``QUOTE_MINIMAL`` — fields containing ``,``, ``"`` or newline are
  wrapped in double quotes and embedded quotes are doubled).
- Decimal → str via ``str(Decimal)`` to preserve every digit. Trailing
  zeros are kept (e.g. ``"100.00000000"``); the caller can post-process
  if they want them stripped.
- ``account_name`` columns are populated via an in-process
  ``account_id → name`` map fetched from ``PortfolioAccountRepo``;
  service-level R2 (no raw SQL) is preserved.
- Empty exports still return a CSV with the header row — the file is
  always valid, never zero-bytes.
- ``export_positions`` does NOT call the live price fetcher (yfinance
  is flaky in batch contexts). It reads the latest ``stock_prices`` row
  via ``PriceLookupRepo.latest_two_closes_batch`` and falls back to
  ``avg_cost`` when the symbol has no daily history.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING

from app.config import settings
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.pnl import summarize
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioDividendRepo,
    PortfolioPositionRepo,
    PortfolioTradeRepo,
)
from app.repositories.portfolio.price_lookup_repo import PriceLookupRepo
from app.services.portfolio.exceptions import TierFeatureUnavailable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.dividend import PortfolioDividend
    from app.db.models.portfolio.trade import PortfolioTrade
    from app.models.user import User


# UTF-8 BOM so Excel detects the encoding for non-ASCII columns
# (Chinese note / broker name). The string form is exactly three bytes
# (``\xef\xbb\xbf``) once .encode("utf-8") is applied.
_BOM = "﻿"


class CsvExportService:
    """Generate CSV bytes from portfolio data.

    One instance per request. Stateless across calls — callers may build
    multiple CSVs from a single instance without side effects.
    """

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._account_repo = PortfolioAccountRepo(db)
        self._trade_repo = PortfolioTradeRepo(db)
        self._position_repo = PortfolioPositionRepo(db)
        self._dividend_repo = PortfolioDividendRepo(db)
        self._price_lookup_repo = PriceLookupRepo(db)

    # ── gates ──────────────────────────────────────────────────────────

    def _assert_tax_export_feature(self) -> None:
        """Block when the user's tier lacks ``tax_export``.

        Per ``config/tier_limits.yaml`` only PRO ships this feature on;
        FREE / BASIC raise ``TierFeatureUnavailable`` which the API layer
        translates to ``403 feature_unavailable:tax_export``.
        """
        if not settings.enable_monetization:
            return
        if not has_feature(self._user.tier, "tax_export"):
            raise TierFeatureUnavailable(feature="tax_export")

    # ── helpers ────────────────────────────────────────────────────────

    async def _account_name_map(self) -> dict[int, str]:
        """Build ``{account_id: name}`` once per export so we never JOIN
        in a hot loop. The user's account count is bounded by tier
        (PRO unlimited but practical < 10) so a full list is cheap.
        """
        rows = await self._account_repo.list_by_user(self._user.id)
        return {a.id: a.name for a in rows}

    @staticmethod
    def _dec(value: Decimal | None) -> str:
        """Decimal → string for CSV. None becomes empty cell."""
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _write_rows(header: list[str], rows: list[list[str]]) -> bytes:
        """Common writer: BOM + header + body, UTF-8 encoded.

        Always uses ``csv.writer`` so fields with commas, quotes, or
        newlines are properly escaped (QUOTE_MINIMAL default).
        """
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
        body = _BOM + buf.getvalue()
        return body.encode("utf-8")

    # ── public API ─────────────────────────────────────────────────────

    async def export_trades(
        self,
        account_id: int | None = None,
        date_from: date_type | None = None,
        date_to: date_type | None = None,
    ) -> bytes:
        """CSV of every trade visible to the user.

        Columns: ``trade_date, account_name, action, symbol, market,
        quantity, price, fee, tax, total_value, note``.

        Filters:
          * ``account_id``  — scope to one account (must be owned).
          * ``date_from / date_to`` — inclusive date filters on
            ``trade_date``.

        ``total_value`` is ``quantity * price`` (gross, no fee/tax
        adjustment) — convenience column for tax reporting where the
        gross trade total drives capital-gains math.
        """
        self._assert_tax_export_feature()
        name_map = await self._account_name_map()

        # Pull all trades for relevant accounts. We page through
        # list_by_account when account_id is supplied, otherwise we
        # walk every owned account. Phase 1 user volumes (BASIC cap 200
        # trades/month, PRO unlimited but bounded by reality) keep this
        # well under a thousand rows for any realistic export.
        trades_all: list[PortfolioTrade] = []
        if account_id is not None:
            if account_id not in name_map:
                # Cross-user / unknown — return empty CSV with header so
                # the contract stays total.
                return self._write_rows(_TRADE_HEADER, [])
            trades_all = await self._collect_trades_for_account(account_id)
        else:
            for aid in name_map:
                trades_all.extend(await self._collect_trades_for_account(aid))

        # Filter by date range in Python (cheap; rows already in memory).
        if date_from is not None:
            trades_all = [t for t in trades_all if t.trade_date >= date_from]
        if date_to is not None:
            trades_all = [t for t in trades_all if t.trade_date <= date_to]

        # Stable ordering: trade_date ASC, id ASC so CSV diffs are
        # predictable across runs.
        trades_all.sort(key=lambda t: (t.trade_date, t.id))

        rows: list[list[str]] = []
        for t in trades_all:
            qty = t.quantity or Decimal("0")
            price = t.price or Decimal("0")
            total_value = qty * price if t.quantity and t.price else Decimal("0")
            rows.append(
                [
                    t.trade_date.isoformat(),
                    name_map.get(t.account_id, ""),
                    t.action,
                    t.symbol,
                    t.market.value if t.market else "",
                    self._dec(t.quantity),
                    self._dec(t.price),
                    self._dec(t.fee),
                    self._dec(t.tax),
                    self._dec(total_value),
                    t.note or "",
                ]
            )
        return self._write_rows(_TRADE_HEADER, rows)

    async def export_positions(self, account_id: int | None = None) -> bytes:
        """CSV of every position roll-up.

        Columns: ``account_name, symbol, market, quantity, avg_cost,
        last_price, total_cost, market_value, unrealized_pnl,
        realized_pnl, is_closed``.

        ``last_price`` comes from the latest ``stock_prices`` row (via
        ``PriceLookupRepo``) rather than the live yfinance fetcher —
        export should be deterministic and not flake on rate limits.
        When no daily close exists, ``last_price`` is blank and
        ``market_value`` / ``unrealized_pnl`` fall back to ``total_cost``
        / ``0`` respectively so the row stays valid.
        """
        self._assert_tax_export_feature()
        name_map = await self._account_name_map()

        if account_id is not None:
            if account_id not in name_map:
                return self._write_rows(_POSITION_HEADER, [])
            positions = await self._position_repo.list_by_account(account_id)
        else:
            positions = await self._position_repo.list_by_user(self._user.id)

        # Batch the price lookup so we don't issue one query per symbol.
        symbols = sorted({p.symbol for p in positions})
        price_map = (
            await self._price_lookup_repo.latest_two_closes_batch(symbols) if symbols else {}
        )

        # Stable ordering for diff-friendly exports.
        positions.sort(key=lambda p: (p.account_id, p.symbol))

        rows: list[list[str]] = []
        for p in positions:
            qty = p.quantity or Decimal("0")
            avg = p.avg_cost_fifo
            total_cost = p.total_cost
            latest_rows = price_map.get(p.symbol, [])
            last_price = latest_rows[0].close if latest_rows else None
            if last_price is not None and qty > Decimal("0"):
                market_value = last_price * qty
                avg_for_calc = avg if avg is not None else Decimal("0")
                unrealized = (last_price - avg_for_calc) * qty
            else:
                market_value = total_cost if total_cost is not None else None
                unrealized = Decimal("0")
            rows.append(
                [
                    name_map.get(p.account_id, ""),
                    p.symbol,
                    p.market.value if p.market else "",
                    self._dec(qty),
                    self._dec(avg),
                    self._dec(last_price),
                    self._dec(total_cost),
                    self._dec(market_value),
                    self._dec(unrealized),
                    self._dec(p.realized_pnl or Decimal("0")),
                    "true" if p.is_closed else "false",
                ]
            )
        return self._write_rows(_POSITION_HEADER, rows)

    async def export_dividends(
        self,
        account_id: int | None = None,
        date_from: date_type | None = None,
        date_to: date_type | None = None,
    ) -> bytes:
        """CSV of every dividend visible to the user.

        Columns: ``ex_date, pay_date, account_name, symbol, market,
        dividend_type, amount_per_share, quantity_at_record,
        withholding_tax, total_amount, net_amount, currency, note``.

        ``total_amount`` and ``net_amount`` mirror the schema computed
        fields (gross = amount_per_share * quantity_at_record; net =
        gross - withholding_tax). Filtering is on ``ex_dividend_date``.
        """
        self._assert_tax_export_feature()
        name_map = await self._account_name_map()

        if account_id is not None:
            if account_id not in name_map:
                return self._write_rows(_DIVIDEND_HEADER, [])
            dividends = await self._collect_dividends_for_account(account_id)
        else:
            dividends = []
            for aid in name_map:
                dividends.extend(await self._collect_dividends_for_account(aid))

        if date_from is not None:
            dividends = [d for d in dividends if d.ex_dividend_date >= date_from]
        if date_to is not None:
            dividends = [d for d in dividends if d.ex_dividend_date <= date_to]
        dividends.sort(key=lambda d: (d.ex_dividend_date, d.id))

        rows: list[list[str]] = []
        for d in dividends:
            amount = d.amount_per_share or Decimal("0")
            qty_at_record = d.quantity_at_record or Decimal("0")
            withholding = d.withholding_tax or Decimal("0")
            total_amount = amount * qty_at_record
            net_amount = total_amount - withholding
            rows.append(
                [
                    d.ex_dividend_date.isoformat(),
                    d.pay_date.isoformat() if d.pay_date else "",
                    name_map.get(d.account_id, ""),
                    d.symbol,
                    d.market.value if d.market else "",
                    d.dividend_type,
                    self._dec(amount),
                    self._dec(qty_at_record),
                    self._dec(withholding),
                    self._dec(total_amount),
                    self._dec(net_amount),
                    d.currency or "",
                    d.note or "",
                ]
            )
        return self._write_rows(_DIVIDEND_HEADER, rows)

    async def export_summary(self) -> bytes:
        """Single-row CSV summary of the user's whole portfolio.

        Columns: ``total_cost, total_value, unrealized_pnl, daily_change,
        gain_simple, gain_simple_pct, position_count, account_count,
        exported_at``.

        ``total_value`` / ``daily_change`` use the latest ``stock_prices``
        close (same reasoning as ``export_positions``). When a symbol
        has no history, ``last_price`` falls back to ``avg_cost`` so the
        summary still balances (zero unrealized contribution).

        ``exported_at`` is an ISO-8601 UTC timestamp letting downstream
        tooling tell apart multiple exports of the same data set.
        """
        self._assert_tax_export_feature()

        positions = await self._position_repo.list_by_user(self._user.id)
        open_positions = [p for p in positions if (p.quantity or Decimal("0")) > Decimal("0")]
        symbols = sorted({p.symbol for p in open_positions})
        price_map = (
            await self._price_lookup_repo.latest_two_closes_batch(symbols) if symbols else {}
        )

        rows_for_summarize: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
        for p in open_positions:
            qty = p.quantity or Decimal("0")
            avg = p.avg_cost_fifo or Decimal("0")
            latest_rows = price_map.get(p.symbol, [])
            if latest_rows:
                last_price = latest_rows[0].close
                prev_close = latest_rows[1].close if len(latest_rows) > 1 else last_price
            else:
                # No price history — degrade gracefully so the summary
                # still reflects cost basis without NaN.
                last_price = avg
                prev_close = avg
            rows_for_summarize.append((qty, avg, last_price, prev_close))

        summary = summarize(rows_for_summarize)
        position_count = await self._position_repo.count_by_user(self._user.id)
        account_count = await self._account_repo.count_by_user(self._user.id)

        exported_at = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"
        rows = [
            [
                self._dec(summary.total_cost),
                self._dec(summary.total_value),
                self._dec(summary.total_unrealized_pnl),
                self._dec(summary.total_daily_change),
                self._dec(summary.gain_simple),
                self._dec(summary.gain_simple_pct),
                str(position_count),
                str(account_count),
                exported_at,
            ]
        ]
        return self._write_rows(_SUMMARY_HEADER, rows)

    # ── private collectors (pagination wrappers) ───────────────────────

    async def _collect_trades_for_account(self, account_id: int) -> list[PortfolioTrade]:
        """Paginate through every trade on the account. Same loop
        pattern as ``PortfolioTradeService._list_all_trades_for_position``
        — repo caps each page at 500 which keeps memory bounded."""
        page_size = 500
        offset = 0
        out: list[PortfolioTrade] = []
        while True:
            page = await self._trade_repo.list_by_account(
                account_id=account_id,
                user_id=self._user.id,
                limit=page_size,
                offset=offset,
            )
            if not page:
                break
            out.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return out

    async def _collect_dividends_for_account(
        self, account_id: int
    ) -> list[PortfolioDividend]:
        """Same pattern for dividends. Each repo page caps at 500."""
        page_size = 500
        offset = 0
        out: list[PortfolioDividend] = []
        while True:
            page = await self._dividend_repo.list_by_account(
                account_id=account_id,
                user_id=self._user.id,
                limit=page_size,
                offset=offset,
            )
            if not page:
                break
            out.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return out


# ── CSV column constants ────────────────────────────────────────────────


_TRADE_HEADER = [
    "trade_date",
    "account_name",
    "action",
    "symbol",
    "market",
    "quantity",
    "price",
    "fee",
    "tax",
    "total_value",
    "note",
]


_POSITION_HEADER = [
    "account_name",
    "symbol",
    "market",
    "quantity",
    "avg_cost",
    "last_price",
    "total_cost",
    "market_value",
    "unrealized_pnl",
    "realized_pnl",
    "is_closed",
]


_DIVIDEND_HEADER = [
    "ex_date",
    "pay_date",
    "account_name",
    "symbol",
    "market",
    "dividend_type",
    "amount_per_share",
    "quantity_at_record",
    "withholding_tax",
    "total_amount",
    "net_amount",
    "currency",
    "note",
]


_SUMMARY_HEADER = [
    "total_cost",
    "total_value",
    "unrealized_pnl",
    "daily_change",
    "gain_simple",
    "gain_simple_pct",
    "position_count",
    "account_count",
    "exported_at",
]


__all__ = ["CsvExportService"]
