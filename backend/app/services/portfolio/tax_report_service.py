"""TaxReportService — Form 8949 / Schedule D capital-gains export.

Phase 4+ tax export (Round 10). Builds on the existing
`CsvExportService` (Y3 Round 4) for the simple trade/position dumps;
this service adds two **matched-pair** reports that US filers need at
tax time:

    * GET /holdings/exports/form8949.csv
      One row per buy-lot consumed by a SELL. Columns mirror
      IRS Form 8949: Description / Date Acquired / Date Sold /
      Proceeds / Cost Basis / Code / Adjustment / Gain-Loss.

    * GET /holdings/exports/schedule_d.csv
      Per-tax-year rollup with short-term + long-term subtotals.

Tier gate: same `tax_export` feature flag as `CsvExportService` (PRO
only per `config/tier_limits.yaml`). The service is the second line of
defence — even if an API guard is missing, the feature check fires
inside every public method.

Anti-coupling (spec §11):
    * No raw SQL — all DB I/O via the repos.
    * No FIFO math here — `tax_report.compute_matched_pairs` is the
      pure-domain layer.
    * Service receives an `AsyncSession`; never opens its own.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.modules.billing.tier_limits import has_feature
from app.modules.portfolio.tax_report import (
    TaxLotMatch,
    TaxYearSummary,
    compute_matched_pairs,
    summarize_by_year,
)
from app.modules.portfolio.wash_sale_detector import (
    WashSaleAdjustment,
    apply_wash_sale_adjustments,
    detect_wash_sales,
)
from app.repositories.portfolio import (
    PortfolioAccountRepo,
    PortfolioTradeRepo,
)
from app.services.portfolio.exceptions import TierFeatureUnavailable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.portfolio.trade import PortfolioTrade
    from app.models.user import User


# UTF-8 BOM — same constant as `export_service.py` so the two CSV exports
# look identical when opened in Excel.
_BOM = "﻿"


_FORM_8949_HEADER = [
    "Description",  # `{quantity} {symbol} ({market})`
    "Date Acquired",  # ISO-8601
    "Date Sold",  # ISO-8601
    "Proceeds",  # net of allocated SELL fee/tax
    "Cost Basis",  # gross BUY cost + allocated BUY fee
    "Code",  # IRS adjustment code (blank today)
    "Adjustment",  # IRS adjustment amount (blank today)
    "Gain/Loss",  # proceeds - cost_basis
    "Term",  # SHORT / LONG — convenience column, not on the IRS form
    "Holding Period Days",  # convenience column for audit
    "Wash Sale",  # placeholder (always "false")
]


_SCHEDULE_D_HEADER = [
    "tax_year",
    "short_term_gain",
    "short_term_loss",
    "short_term_net",
    "long_term_gain",
    "long_term_loss",
    "long_term_net",
    "total_net",
    "total_matches",
]


class TaxReportService:
    """Capital-gains tax report service.

    One instance per request. Stateless across calls.
    """

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user
        self._account_repo = PortfolioAccountRepo(db)
        self._trade_repo = PortfolioTradeRepo(db)

    # ── tier gate ──────────────────────────────────────────────────────

    def _assert_tax_export_feature(self) -> None:
        """Block FREE / BASIC tiers. PRO passes. Bypassed in dev/test."""
        if not settings.enable_monetization:
            return
        if not has_feature(self._user.tier, "tax_export"):
            raise TierFeatureUnavailable(feature="tax_export")

    # ── public API ─────────────────────────────────────────────────────

    async def generate_form_8949(
        self,
        account_id: int | None = None,
        tax_year: int | None = None,
    ) -> tuple[list[TaxLotMatch], dict[int, TaxYearSummary]]:
        """Compute matched pairs + per-year summary for the caller.

        Algorithm:
            1. Tier check.
            2. Load every trade visible to the user (filter by
               `account_id` when given).
            3. Project ORM rows into the dict shapes that
               `tax_report.compute_matched_pairs` consumes (BUY lots
               history + SELL trades).
            4. Run the FIFO matcher.
            5. Optionally filter matches to `tax_year` (by sale_date).
            6. Roll up matches to per-year summaries.

        Returns:
            (matches, summary_by_year) — both empty when the user has
            no taxable activity. The summary dict's keys are years
            present in `matches` only; absent years are absent (not
            zero rows).

        Raises:
            TierFeatureUnavailable: caller's tier lacks `tax_export`.
        """
        self._assert_tax_export_feature()

        trades = await self._collect_user_trades(account_id=account_id)
        buy_lots, sell_trades = _project_trades(trades)

        # `compute_matched_pairs` is pure — works on the dict view.
        matches = compute_matched_pairs(buy_lots, sell_trades)

        if tax_year is not None:
            matches = [m for m in matches if m.sale_date.year == tax_year]

        summary = summarize_by_year(matches)
        return matches, summary

    async def generate_form_8949_with_wash_sales(
        self,
        account_id: int | None = None,
        tax_year: int | None = None,
    ) -> tuple[
        list[TaxLotMatch],
        list[WashSaleAdjustment],
        dict[int, TaxYearSummary],
    ]:
        """Like `generate_form_8949` but also runs §1091 wash-sale detection.

        Algorithm:
            1. Tier check + load trades (re-uses the private collectors).
            2. Run FIFO matcher → ``matches`` (raw, pre-wash-sale).
            3. Run `detect_wash_sales(trades, matches)` → adjustments.
            4. Fold adjustments back into matches via
               `apply_wash_sale_adjustments` (frozen-dataclass rebuild).
            5. Optional `tax_year` filter on `sale_date`.
            6. `summarize_by_year` on the *adjusted* matches so the
               year totals already reflect disallowed-loss zero-outs.

        Returns:
            (adjusted_matches, adjustments, summary_by_year)

        Raises:
            TierFeatureUnavailable: caller's tier lacks ``tax_export``.
        """
        self._assert_tax_export_feature()

        trades = await self._collect_user_trades(account_id=account_id)
        buy_lots, sell_trades = _project_trades(trades)
        matches = compute_matched_pairs(buy_lots, sell_trades)

        # Detector needs the full trade list (BUYs to scan as
        # replacement candidates), projected to the dict shape it
        # consumes — see `_project_trades_for_wash_sale`.
        trade_dicts = _project_trades_for_wash_sale(trades)
        result = detect_wash_sales(trade_dicts, matches)
        adjusted = apply_wash_sale_adjustments(matches, result.adjustments)

        if tax_year is not None:
            adjusted = [m for m in adjusted if m.sale_date.year == tax_year]

        summary = summarize_by_year(adjusted)
        return adjusted, result.adjustments, summary

    async def export_form_8949_csv(
        self,
        account_id: int | None = None,
        tax_year: int | None = None,
        apply_wash_sales: bool = False,
    ) -> bytes:
        """Return Form 8949-style CSV bytes (UTF-8 + BOM).

        Args:
            account_id / tax_year: standard filters (see
                `generate_form_8949`).
            apply_wash_sales: opt-in flag. When True the export runs
                `generate_form_8949_with_wash_sales` so the **Code** and
                **Adjustment** columns reflect IRS §1091 disallowance.
                Default False for backward compatibility with the
                Round 10 wire format.
        """
        if apply_wash_sales:
            matches, _adj, _summary = await self.generate_form_8949_with_wash_sales(
                account_id=account_id, tax_year=tax_year
            )
        else:
            matches, _ = await self.generate_form_8949(account_id=account_id, tax_year=tax_year)
        rows: list[list[str]] = []
        for m in matches:
            # When the row is a wash sale we emit:
            #   Code = "W"
            #   Adjustment = +disallowed (positive magnitude per IRS form)
            #   Gain/Loss = 0 (loss fully disallowed) — the matcher
            #               already zeroed gain_loss in
            #               apply_wash_sale_adjustments.
            code = "W" if m.is_wash_sale else ""
            adjustment = _dec(m.wash_sale_disallowed_loss) if m.is_wash_sale else ""
            rows.append(
                [
                    f"{_dec(m.quantity)} {m.symbol} ({m.market})",
                    m.acquisition_date.isoformat(),
                    m.sale_date.isoformat(),
                    _dec(m.proceeds),
                    _dec(m.cost_basis),
                    code,
                    adjustment,
                    _dec(m.gain_loss),
                    m.term,
                    str(m.holding_period_days),
                    "true" if m.is_wash_sale else "false",
                ]
            )
        return _write_csv(_FORM_8949_HEADER, rows)

    async def export_year_summary_csv(
        self,
        account_id: int | None = None,
        tax_year: int | None = None,
    ) -> bytes:
        """Return Schedule D-style annual rollup CSV bytes.

        `tax_year` narrows to a single year. Otherwise emits one row
        per year present in the matched-pair set, sorted ASC.
        """
        _, summary = await self.generate_form_8949(account_id=account_id, tax_year=tax_year)
        rows: list[list[str]] = []
        for year in sorted(summary):
            s = summary[year]
            rows.append(
                [
                    str(s.tax_year),
                    _dec(s.short_term_gain),
                    _dec(s.short_term_loss),
                    _dec(s.short_term_net),
                    _dec(s.long_term_gain),
                    _dec(s.long_term_loss),
                    _dec(s.long_term_net),
                    _dec(s.total_net),
                    str(s.total_matches),
                ]
            )
        return _write_csv(_SCHEDULE_D_HEADER, rows)

    # ── private collectors ─────────────────────────────────────────────

    async def _collect_user_trades(self, account_id: int | None) -> list[PortfolioTrade]:
        """Load every BUY/SELL row for the user.

        Walks each owned account (or only the requested one) via the
        repo's paginated list; ownership is enforced by the repo's
        JOIN on `user_id`. We skip non-(BUY|SELL) actions — DIVIDEND
        and SPLIT rows do not contribute to capital-gains math.
        """
        accounts = await self._account_repo.list_by_user(self._user.id)
        owned_ids = {a.id for a in accounts}
        if account_id is not None:
            if account_id not in owned_ids:
                # Unknown / not-owned — return empty so the contract
                # stays total (matches `CsvExportService` behaviour).
                return []
            target_ids = [account_id]
        else:
            target_ids = sorted(owned_ids)

        out: list[PortfolioTrade] = []
        page_size = 500
        for aid in target_ids:
            offset = 0
            while True:
                page = await self._trade_repo.list_by_account(
                    account_id=aid,
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
        return [t for t in out if t.action in ("BUY", "SELL")]


# ── helpers (pure) ──────────────────────────────────────────────────────


def _project_trades(
    trades: list[PortfolioTrade],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ORM trades into the dict shape `tax_report` consumes.

    BUY → contributes to `buy_lots_history`. Cost-per-unit is the gross
    trade price (NOT the lot's fee-adjusted cost_per_unit) so the
    matcher's proportional fee allocation can run independently. The
    BUY's full fee is passed through as `total_fee`.

    SELL → contributes to `sell_trades`. Fee + tax travel as separate
    columns so the matcher can sum them once and allocate
    proportionally across consumed lots.

    Trades with NULL price / qty (defensive — schema allows it for
    DIVIDEND / SPLIT rows but we already filtered those upstream) are
    skipped.
    """
    buys: list[dict[str, Any]] = []
    sells: list[dict[str, Any]] = []
    for t in trades:
        if t.quantity is None or t.price is None:
            continue
        if t.action == "BUY":
            buys.append(
                {
                    "trade_id": t.id,
                    "symbol": t.symbol,
                    "market": t.market.value if t.market else "",
                    "acquisition_date": t.trade_date,
                    "qty": t.quantity,
                    "cost_per_unit": t.price,
                    "total_fee": t.fee or Decimal("0"),
                }
            )
        elif t.action == "SELL":
            sells.append(
                {
                    "trade_id": t.id,
                    "symbol": t.symbol,
                    "market": t.market.value if t.market else "",
                    "sale_date": t.trade_date,
                    "qty": t.quantity,
                    "price_per_unit": t.price,
                    "total_fee": t.fee or Decimal("0"),
                    "total_tax": t.tax or Decimal("0"),
                }
            )
    return buys, sells


def _project_trades_for_wash_sale(
    trades: list[PortfolioTrade],
) -> list[dict[str, Any]]:
    """Project ORM trades into the dict shape `wash_sale_detector` consumes.

    Detector keys: ``id``, ``trade_date``, ``symbol``, ``market``,
    ``action``, ``qty``, ``price`` (price is optional but useful for
    auditing). DIVIDEND / SPLIT rows are filtered out upstream so we
    can safely include every action the caller passed in.
    """
    out: list[dict[str, Any]] = []
    for t in trades:
        if t.quantity is None or t.price is None:
            continue
        out.append(
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "symbol": t.symbol,
                "market": t.market.value if t.market else "",
                "action": t.action,
                "qty": t.quantity,
                "price": t.price,
            }
        )
    return out


def _dec(v: Decimal | None) -> str:
    """Decimal → CSV cell (empty string for None)."""
    if v is None:
        return ""
    return str(v)


def _write_csv(header: list[str], rows: list[list[str]]) -> bytes:
    """Common BOM + UTF-8 CSV writer — mirrors `export_service._write_rows`."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return (_BOM + buf.getvalue()).encode("utf-8")


__all__ = ["TaxReportService"]
