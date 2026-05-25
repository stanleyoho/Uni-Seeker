"""F13FilingService — filings, holdings, diff and on-demand refresh.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2, §7 (domain logic), §11 R4 / R6 (idempotency / amendments).

Owns three user-facing reads and one mutation:

- `list_filings_for_filer`    — historical filings list
- `get_holdings_at_period`    — single-period snapshot
- `compute_diff`              — QoQ delta (delegates to `diff.compute_diff`)
- `refresh_filer`             — Q1 on-demand fetch (the only mutation)

Access control: every read first checks `is_subscribed(user_id,
filer_id)`. The `institutional_ownership_panel` feature flag is a
separate Pro-tier gate used by `F13CrossStockService` for the
per-stock view; this service only handles the per-filer surface so it
relies on subscription gating alone.

Refresh anti-concurrency: a single process-local `asyncio.Lock` per
filer_id keeps two simultaneous refresh requests on the same filer
from racing. Lock acquisition is non-blocking; a busy filer raises
`F13RefreshInFlight` so the API layer can return 429 immediately. The
lock dictionary lives at class scope because we want the lock identity
to survive across request-scoped service instances within the same
process.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.modules.billing.tier_limits import has_feature
from app.modules.institutional.diff import HoldingChange, compute_diff
from app.modules.institutional.edgar_client import (
    EdgarClient,
    EdgarTransientError,
    FilingMetadata,
)
from app.modules.institutional.parser import (
    ParsedHolding,
    ParseError,
    parse_infotable_xml,
    summarize_filing,
)
from app.repositories.institutional import (
    F13FilerRepo,
    F13FilingRepo,
    F13HoldingRepo,
    F13UserSubscriptionRepo,
)
from app.services.audit import log_audit_event
from app.services.institutional.exceptions import (
    F13EdgarError,
    F13FilerNotFound,
    F13FilingNotFound,
    F13RefreshInFlight,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.institutional.filing import F13Filing
    from app.db.models.institutional.holding import F13Holding
    from app.models.user import User

logger = structlog.get_logger(__name__)


class F13FilingService:
    """Filings + holdings + on-demand refresh."""

    # Process-local locks keyed by filer_id. Each lock guards
    # `refresh_filer` for that filer so concurrent requests degrade
    # cleanly to 429 instead of racing on the DB. Dict mutation itself
    # is protected by `_locks_guard` because asyncio.Lock() construction
    # must not race when two coroutines first ask for the same key.
    _locks: dict[int, asyncio.Lock] = {}
    _locks_guard: asyncio.Lock = asyncio.Lock()

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        edgar_client: EdgarClient,
    ) -> None:
        self._db = db
        self._user = user
        self._edgar = edgar_client
        self._filer_repo = F13FilerRepo(db)
        self._filing_repo = F13FilingRepo(db)
        self._holding_repo = F13HoldingRepo(db)
        self._sub_repo = F13UserSubscriptionRepo(db)

    # ── access control helpers ─────────────────────────────────────────

    async def _require_filer(self, filer_id: int):
        filer = await self._filer_repo.get_by_id(filer_id)
        if filer is None:
            raise F13FilerNotFound(f"filer_id={filer_id} not found")
        return filer

    async def _require_subscribed(self, filer_id: int) -> None:
        """Per spec §6.2: filings/holdings are gated by subscription.

        We collapse "filer doesn't exist" and "not subscribed" into the
        same `F13FilerNotFound` to avoid leaking existence (same
        information-hiding convention as portfolio module's
        `PortfolioAccountNotFound`).
        """
        if not await self._sub_repo.is_subscribed(self._user.id, filer_id):
            # Whether the filer exists or not is intentionally indistinguishable
            raise F13FilerNotFound(f"filer_id={filer_id} not accessible")

    # ── reads ──────────────────────────────────────────────────────────

    async def list_filings_for_filer(
        self, filer_id: int, limit: int = 20, offset: int = 0
    ) -> list[F13Filing]:
        await self._require_subscribed(filer_id)
        return await self._filing_repo.list_by_filer(filer_id, limit=limit, offset=offset)

    async def get_holdings_at_period(
        self, filer_id: int, period: str = "latest"
    ) -> tuple[F13Filing, list[F13Holding]]:
        """Return (filing, holdings) for the requested period.

        Args:
            filer_id: subscribed filer id.
            period:   "latest" or ISO date string ("2025-12-31").
                      ISO dates resolve to an exact `report_period_end`
                      match (amendment-aware — picks the row with the
                      most recent `filed_at` when both 13F-HR and
                      13F-HR/A exist for the same quarter).

        Raises:
            F13FilerNotFound — caller not subscribed.
            F13FilingNotFound — period exists but no filing is loaded
                (caller should hit refresh first), or ISO date doesn't
                match any stored filing.
            ValueError — malformed `period` string.
        """
        await self._require_subscribed(filer_id)

        filing: F13Filing | None
        if period == "latest":
            filing = await self._filing_repo.get_latest_for_filer(filer_id)
        else:
            try:
                target = date.fromisoformat(period)
            except ValueError as exc:
                raise ValueError(f"period must be 'latest' or ISO date, got {period!r}") from exc
            filing = await self._filing_repo.get_at_period(filer_id, target)

        if filing is None:
            raise F13FilingNotFound(f"no filing for filer_id={filer_id} period={period}")
        holdings = await self._holding_repo.list_by_filing(filing.id)
        return filing, holdings

    async def compute_diff(
        self,
        filer_id: int,
        from_date: date,
        to_date: date,
    ) -> tuple[list[F13Holding], list[F13Holding], list[HoldingChange]]:
        """QoQ diff between two stored periods.

        Returns `(prev_holdings, curr_holdings, changes)` so the API
        layer can render both sides + the diff in one round trip.
        Diff engine is pure (`app.modules.institutional.diff`); this
        method translates ORM rows to its `ParsedHolding` input shape
        and back is unnecessary — `HoldingChange` carries the diff
        directly.

        Raises:
            F13FilerNotFound  — caller not subscribed.
            F13FilingNotFound — either period has no stored filing.
        """
        await self._require_subscribed(filer_id)
        prev_filing = await self._filing_repo.get_at_period(filer_id, from_date)
        curr_filing = await self._filing_repo.get_at_period(filer_id, to_date)
        if prev_filing is None or curr_filing is None:
            raise F13FilingNotFound(
                f"missing filing(s) for diff: filer_id={filer_id} from={from_date} to={to_date}"
            )
        prev_rows = await self._holding_repo.list_by_filing(prev_filing.id)
        curr_rows = await self._holding_repo.list_by_filing(curr_filing.id)
        # Adapt ORM rows → ParsedHolding for the pure diff engine.
        prev_parsed = [_orm_holding_to_parsed(r) for r in prev_rows]
        curr_parsed = [_orm_holding_to_parsed(r) for r in curr_rows]
        changes = compute_diff(prev_parsed, curr_parsed)
        return prev_rows, curr_rows, changes

    async def get_holding_history(
        self,
        filer_id: int,
        identifier: str,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 20,
    ) -> dict:
        """Per-stock time-series across multiple quarterly filings.

        Replaces the frontend's "N parallel useHoldings + filter"
        pattern with a single round trip. Returns a plain dict that
        the API layer wraps in `F13HoldingHistoryResponse`.

        Access control: caller is allowed iff
            - the user is subscribed to `filer_id`, OR
            - the user's tier carries `institutional_ownership_panel`
              (Pro). The Pro bypass exists because the cross-stock
              panel already lets a Pro user inspect any filer's
              positions on a stock; this endpoint is the per-filer
              counterpart and must offer the same reach.
          We do NOT collapse the two failure cases into a single 404:
          when the user is subscribed but the identifier never
          appeared in any filing within the window, we return an
          empty `entries` list with `cusip=symbol=None`. That keeps
          the timeline component renderable as "filed but never held".

        Algorithm:
          1. Validate access (subscription OR Pro feature flag).
          2. Default window: 2 years ago → today (inclusive).
          3. Pull ASC-sorted `(filing, holding | None)` tuples via the
             repo.
          4. Collapse same-period amendments by keeping the row with
             the most recent `filed_at` (mirrors `get_at_period`).
          5. Walk forward computing deltas + change_type:
             - prev NOT_HELD, curr held → NEW
             - prev held, curr NOT_HELD → EXITED
             - prev held, curr held → INCREASED / DECREASED / UNCHANGED
             - prev NOT_HELD, curr NOT_HELD → NOT_HELD
          6. Pick `cusip` / `symbol` from the first held entry (when
             any) so the response carries display metadata.

        Args:
            filer_id: subscribed filer id.
            identifier: CUSIP (9 chars) or stock symbol. Matched as
                CUSIP first; falls back to `stocks.symbol` JOIN when
                the holding has been mapped.
            from_date: inclusive lower bound. Defaults to 2y ago.
            to_date: inclusive upper bound. Defaults to today.
            limit: max number of filings to consider (bounded by the
                filings count). Defaults to 20.

        Raises:
            F13FilerNotFound: caller has neither a subscription nor
                the Pro feature flag for this filer.
        """
        # Step 1: access control — subscription OR Pro feature bypass.
        # `_require_subscribed` already collapses "filer missing" and
        # "not yours" into the same 404; we mirror that for the Pro
        # branch by requiring the filer to exist before bypassing.
        if not await self._sub_repo.is_subscribed(self._user.id, filer_id):
            pro_bypass = not settings.enable_monetization or has_feature(
                self._user.tier, "institutional_ownership_panel"
            )
            if not pro_bypass:
                raise F13FilerNotFound(f"filer_id={filer_id} not accessible")
            # Pro bypass still needs the filer to exist so we don't
            # return a phantom timeline. Re-use `_require_filer` —
            # raises `F13FilerNotFound` when missing.
            await self._require_filer(filer_id)

        # Step 2: resolve the window.
        if to_date is None:
            to_date = date.today()
        if from_date is None:
            # 2y default. Use 730 days for a stable arithmetic window
            # — leap-year drift is irrelevant at quarter granularity.
            from_date = to_date - timedelta(days=730)
        if from_date > to_date:
            # Empty window: short-circuit with an empty response so
            # the caller doesn't have to special-case it.
            return {
                "filer_id": filer_id,
                "cusip": None,
                "symbol": None,
                "entries": [],
            }

        # Step 3: repo query (ASC sorted, LEFT join on identifier).
        tuples = await self._holding_repo.list_history_for_filer_and_symbol(
            filer_id=filer_id,
            identifier=identifier,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )

        # Step 4: amendment collapse. When (filing.report_period_end)
        # appears twice (13F-HR + 13F-HR/A), keep the one with the
        # latest `filed_at`. The tuples are ASC by period_end already
        # so we walk once and overwrite on conflict.
        by_period: dict[date, tuple] = {}
        for filing, holding in tuples:
            existing = by_period.get(filing.report_period_end)
            if existing is None or filing.filed_at > existing[0].filed_at:
                by_period[filing.report_period_end] = (filing, holding)
        collapsed = [by_period[k] for k in sorted(by_period.keys())]

        # Step 5: walk forward + compute deltas.
        entries: list[dict] = []
        prev_shares: Decimal | None = None
        cusip_out: str | None = None
        symbol_out: str | None = None

        for filing, holding in collapsed:
            if holding is None:
                # Filed but didn't hold the requested stock.
                shares = None
                value_usd = None
                put_call = None
                investment_discretion = None
            else:
                shares = holding.shares
                value_usd = holding.value_usd
                put_call = holding.put_call
                investment_discretion = holding.investment_discretion
                # Capture display metadata from the first match.
                if cusip_out is None:
                    cusip_out = holding.cusip
                if symbol_out is None and holding.stock_id is not None:
                    symbol_out = await self._resolve_stock_symbol(holding.stock_id)

            # change_type + deltas
            change_type, delta_shares, delta_pct = _classify_history_point(
                prev_shares=prev_shares,
                curr_shares=shares,
            )

            entries.append(
                {
                    "filing_id": filing.id,
                    "report_period_end": filing.report_period_end,
                    "form_type": filing.form_type,
                    "shares": shares,
                    "value_usd": value_usd,
                    "put_call": put_call,
                    "investment_discretion": investment_discretion,
                    "delta_shares": delta_shares,
                    "delta_pct": delta_pct,
                    "change_type": change_type,
                }
            )
            prev_shares = shares

        return {
            "filer_id": filer_id,
            "cusip": cusip_out,
            "symbol": symbol_out,
            "entries": entries,
        }

    async def _resolve_stock_symbol(self, stock_id: int) -> str | None:
        """Look up `stocks.symbol` for the holding's stock_id.

        Used only to populate the response envelope's `symbol` field —
        the timeline itself does not depend on the lookup, so a miss
        (deleted stock row, race with the SET NULL FK) just leaves
        `symbol` as None.
        """
        from sqlalchemy import select

        from app.models.stock import Stock

        result = await self._db.execute(select(Stock.symbol).where(Stock.id == stock_id))
        return result.scalar_one_or_none()

    # ── on-demand refresh (Q1) ─────────────────────────────────────────

    async def refresh_filer(self, filer_id: int, max_quarters: int = 4) -> dict[str, int]:
        """Fetch + persist the most recent N quarterly 13F filings.

        Algorithm (spec §6.2 + Q1 + Q8 backfill = 4):
          1. Verify filer exists and the user is subscribed.
          2. Acquire the per-filer lock non-blockingly → 429 if held.
          3. List filings on EDGAR for the filer (`max_count=N`).
          4. For each filing not yet in DB (exists() probe):
               a. Fetch infotable XML.
               b. Parse → list[ParsedHolding].
               c. Summarise → totals.
               d. Insert filing row + bulk-insert holdings.
          5. Update filer.latest_* from the most recent stored filing.
          6. Audit log + return counts.

        Anti-concurrency: process-local asyncio lock per filer_id. A
        second concurrent caller raises `F13RefreshInFlight`. We do
        NOT use the DB updated_at timestamp as a rate limiter here
        because (a) it requires a writable session for the timestamp
        bump even on a no-op refresh, (b) the spec only asked for
        anti-concurrent, not anti-frequency.

        Returns:
            dict {filings_added: int, holdings_added: int}.

        Raises:
            F13FilerNotFound    — filer missing or user not subscribed.
            F13RefreshInFlight  — another coroutine is refreshing.
            F13EdgarError       — EDGAR fetch failed after retries.
        """
        # Step 1: access control
        filer = await self._require_filer(filer_id)
        await self._require_subscribed(filer_id)

        # Step 2: acquire lock non-blockingly
        lock = await self._get_lock(filer_id)
        if lock.locked():
            raise F13RefreshInFlight(filer_id=filer_id)
        async with lock:
            return await self._do_refresh(filer, max_quarters)

    async def _do_refresh(self, filer, max_quarters: int) -> dict[str, int]:
        """Inner refresh body — runs under the per-filer lock."""
        # Step 3: list filings on EDGAR
        try:
            edgar_filings = await self._edgar.list_filings_for_filer(
                filer.cik, max_count=max_quarters
            )
        except EdgarTransientError as exc:
            raise F13EdgarError(
                f"EDGAR list_filings_for_filer failed: {exc}",
                edgar_status=None,
            ) from exc

        filings_added = 0
        holdings_added = 0
        # Track ORM rows we just inserted so the notification service
        # can fan out alerts without re-querying the DB. Empty list
        # means "no new filings this cycle" — common case.
        newly_inserted: list[F13Filing] = []

        # Step 4: ingest each new filing
        for meta in edgar_filings:
            if await self._filing_repo.exists(filer.id, meta.accession_number):
                continue
            if meta.raw_xml_url is None:
                # EdgarClient could not resolve the real infotable XML
                # via the filing's index.json (e.g. SEC changed layout
                # or network glitch). Skip rather than insert a half-row
                # we can't backfill — next refresh tick will retry.
                logger.warning(
                    "f13_refresh_skipped_no_infotable_url",
                    filer_id=filer.id,
                    accession=meta.accession_number,
                    form_type=meta.form_type,
                )
                continue
            inserted_filing, holdings_inserted = await self._ingest_one(filer.id, meta)
            filings_added += 1
            holdings_added += holdings_inserted
            newly_inserted.append(inserted_filing)

        # Step 5: refresh filer.latest_* from the freshest stored filing
        latest = await self._filing_repo.get_latest_for_filer(filer.id)
        if latest is not None:
            await self._filer_repo.update_latest_aum(
                filer_id=filer.id,
                total_value_usd=latest.total_value_usd or Decimal("0"),
                options_notional_usd=(latest.options_notional_usd or Decimal("0")),
                position_count=latest.total_positions or 0,
                filing_date=latest.report_period_end,
            )

        # Step 6: audit log
        await log_audit_event(
            self._db,
            action="f13_filer_refreshed",
            user_id=self._user.id,
            resource_type="f13_filer",
            resource_id=str(filer.id),
            after_state={
                "filings_added": filings_added,
                "holdings_added": holdings_added,
                "max_quarters": max_quarters,
            },
        )

        # Step 7: fire-and-forget TG fan-out. Notification is a
        # downstream side-effect — it MUST NOT roll back the refresh
        # row even if the TG API is down. We:
        #   1. Flush so the new filings have stable IDs (notification
        #      service reads them by ORM row).
        #   2. Run the notify call inline (NOT create_task) because the
        #      service uses the same AsyncSession; spawning a task
        #      while the session is held would cross-thread the
        #      transaction. The cost is a few hundred ms per filing
        #      in the refresh path — acceptable for a Q1 on-demand
        #      flow, and we can move this off-thread (Plan 8 queue)
        #      when scale demands.
        # Any exception from the notifier is logged + swallowed.
        if newly_inserted:
            try:
                from app.services.institutional.notification_service import (
                    F13NotificationService,
                )

                notifier = F13NotificationService(self._db)
                await notifier.notify_new_filings(filer.id, newly_inserted)
            except Exception as exc:  # pragma: no cover - safety net
                logger.warning(
                    "f13_refresh_notify_failed",
                    filer_id=filer.id,
                    error=str(exc),
                )
        return {
            "filings_added": filings_added,
            "holdings_added": holdings_added,
        }

    async def _ingest_one(self, filer_id: int, meta: FilingMetadata) -> tuple[F13Filing, int]:
        """Fetch + parse + persist one new filing.

        Returns ``(filing_row, holdings_count)`` so the caller can both
        update its counter (counts) and collect the new filing rows for
        downstream notification fan-out.

        Caller (``_do_refresh``) guarantees ``meta.raw_xml_url`` is not
        None; we assert here for type-narrowing.
        """
        assert meta.raw_xml_url is not None, "raw_xml_url None should have been filtered upstream"
        try:
            xml_text = await self._edgar.fetch_filing_xml(meta.raw_xml_url)
        except EdgarTransientError as exc:
            raise F13EdgarError(
                f"EDGAR fetch_filing_xml failed: {exc}",
                edgar_status=None,
            ) from exc

        try:
            parsed = parse_infotable_xml(xml_text)
        except ParseError as exc:
            # A single bad XML body should not poison the whole refresh.
            # Log + skip the row by treating it as "no holdings".
            logger.warning(
                "f13_refresh_parse_error",
                filer_id=filer_id,
                accession=meta.accession_number,
                error=str(exc),
            )
            parsed = []

        summary = summarize_filing(parsed)

        # Persist filing meta + holdings in one logical step.
        filing = await self._filing_repo.create(
            filer_id=filer_id,
            accession_number=meta.accession_number,
            form_type=meta.form_type,
            report_period_end=meta.report_period_end,
            filed_at=meta.filed_at,
            total_value_usd=summary.total_value_usd,
            options_notional_usd=summary.options_notional_usd,
            total_positions=summary.total_positions,
            raw_xml_url=meta.raw_xml_url,
        )

        holding_dicts = [_parsed_to_holding_kwargs(p) for p in parsed]
        holdings_count = await self._holding_repo.bulk_insert(
            filing_id=filing.id, holdings=holding_dicts
        )
        return filing, holdings_count

    async def _get_lock(self, filer_id: int) -> asyncio.Lock:
        """Lazily create the per-filer lock under a global guard.

        Without the guard, two coroutines could observe `filer_id not in
        _locks` simultaneously and each create a fresh Lock — defeating
        the anti-concurrency invariant.
        """
        async with self._locks_guard:
            lock = self._locks.get(filer_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[filer_id] = lock
            return lock


# ── module-private helpers (pure functions) ────────────────────────────


def _parsed_to_holding_kwargs(p: ParsedHolding) -> dict:
    """Adapt a `ParsedHolding` dataclass into `F13Holding` constructor
    kwargs. Keeps service layer free of ORM/Decimal coupling decisions
    that are otherwise scattered.

    `stock_id` mapping is intentionally NOT done here — Phase 1 uses
    lazy CUSIP→stock_id lookup (spec §3.4). Holdings ingest with
    `stock_id=None` and a separate job (Phase 2) backfills.
    """
    return {
        "cusip": p.cusip,
        "name_of_issuer": p.name_of_issuer,
        "value_usd": p.value_usd,
        "shares": p.shares,
        "put_call": p.put_call,
        "investment_discretion": p.investment_discretion,
        "voting_authority_sole": p.voting_authority_sole,
        "voting_authority_shared": p.voting_authority_shared,
        "voting_authority_none": p.voting_authority_none,
    }


def _classify_history_point(
    *,
    prev_shares: Decimal | None,
    curr_shares: Decimal | None,
) -> tuple[str, Decimal | None, Decimal | None]:
    """Classify a single (prev, curr) shares pair for the history endpoint.

    Returns ``(change_type, delta_shares, delta_pct)``. The semantics
    extend the 5-way diff classification with a 6th state — NOT_HELD —
    for "filer filed the quarter but didn't hold the requested stock
    that period AND we have no prior position to diff against".

    Rules (in evaluation order):
        prev=None, curr=None  → NOT_HELD,    Δshares=None, Δpct=None
        prev=None, curr=value → NEW,         Δshares=None, Δpct=None
        prev=value, curr=None → EXITED,      Δshares=-prev, Δpct=None
        prev=value, curr=value
            curr > prev       → INCREASED
            curr < prev       → DECREASED
            curr == prev      → UNCHANGED

    Δpct is the percent change vs prev (basis = prev_shares). It is
    None when prev is None / zero or curr is None (no meaningful %
    when one side is missing).
    """
    if prev_shares is None and curr_shares is None:
        return ("NOT_HELD", None, None)
    if prev_shares is None and curr_shares is not None:
        # First time we see the position: NEW. Δshares stays None
        # because there is no prior baseline to subtract from — the
        # frontend renders the bare `shares` instead.
        return ("NEW", None, None)
    if prev_shares is not None and curr_shares is None:
        return ("EXITED", -prev_shares, None)
    # Both non-None.
    assert prev_shares is not None
    assert curr_shares is not None
    delta = curr_shares - prev_shares
    if prev_shares == 0:
        # Divide-by-zero guard. Treat any movement off a zero base as
        # NEW for classification purposes (rare; can happen when a
        # filer reported zero shares in the prior quarter — defensive).
        pct: Decimal | None = None
    else:
        pct = (delta / prev_shares) * Decimal("100")
    if delta > 0:
        return ("INCREASED", delta, pct)
    if delta < 0:
        return ("DECREASED", delta, pct)
    return ("UNCHANGED", delta, pct)


def _orm_holding_to_parsed(row) -> ParsedHolding:
    """Translate an ORM `F13Holding` row into a `ParsedHolding`
    dataclass so the pure diff engine can consume it without coupling
    to SQLAlchemy. Keep this here, not in the domain module (spec
    §11 R1).
    """
    return ParsedHolding(
        cusip=row.cusip,
        name_of_issuer=row.name_of_issuer,
        value_usd=row.value_usd,
        shares=row.shares,
        shares_or_principal_type=("SH" if row.shares is not None else "PRN"),
        put_call=row.put_call,
        investment_discretion=row.investment_discretion or "SOLE",
        voting_authority_sole=row.voting_authority_sole or Decimal("0"),
        voting_authority_shared=row.voting_authority_shared or Decimal("0"),
        voting_authority_none=row.voting_authority_none or Decimal("0"),
    )
