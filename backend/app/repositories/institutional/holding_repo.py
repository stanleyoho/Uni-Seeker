"""F13HoldingRepo — CRUD over `f13_holdings`.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§4.3 Table 4, §6.3.

Most filings carry 30–1000 holding rows; `bulk_insert` is therefore
the hot-path insert API. Single-row inserts would impose unacceptable
round-trip overhead inside the refresh orchestration.

Isolation: **NO `user_id` filter** — holdings hang off a filing which
hangs off a filer (shared). Access control is enforced at the service
layer via subscription check OR Pro-tier `institutional_ownership_panel`
feature flag for cross-filer views.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, select

from app.db.models.institutional.filer import F13Filer
from app.db.models.institutional.filing import F13Filing
from app.db.models.institutional.holding import F13Holding

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class F13HoldingRepo:
    """CRUD over `f13_holdings`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def bulk_insert(
        self, filing_id: int, holdings: list[dict[str, Any]]
    ) -> int:
        """Batch-INSERT holdings rows for one filing. Returns the count.

        Each dict in `holdings` should carry the column kwargs accepted
        by the `F13Holding` constructor (cusip, name_of_issuer,
        value_usd, shares, put_call, investment_discretion,
        voting_authority_*; stock_id optional). Empty input is a no-op
        and returns 0.

        We use `session.add_all` rather than a Core `insert().values(...)`
        bulk because the ORM emits a single multi-row INSERT (or a few
        chunks) on Postgres and we want to keep the cascade /
        relationship invariants behaving consistently. For Phase 1 row
        counts (~1k max per filing) this is fast enough.
        """
        if not holdings:
            return 0
        rows = [F13Holding(filing_id=filing_id, **h) for h in holdings]
        self.db.add_all(rows)
        await self.db.flush()
        return len(rows)

    async def list_by_filing(self, filing_id: int) -> list[F13Holding]:
        """All holdings rows for `filing_id`, ordered by CUSIP ASC.

        Stable order matters for the diff engine + UI tests.
        """
        result = await self.db.execute(
            select(F13Holding)
            .where(F13Holding.filing_id == filing_id)
            .order_by(F13Holding.cusip.asc(), F13Holding.id.asc())
        )
        return list(result.scalars().all())

    async def list_by_filer_at_period(
        self,
        filer_id: int,
        report_period_end: date,
    ) -> list[F13Holding]:
        """JOIN through filings to fetch holdings at a specific period.

        When the filer has both 13F-HR and 13F-HR/A for the period, the
        amendment wins via `filed_at DESC` (matches `filing_repo.get_at_period`
        semantics). Returns empty list when no filing exists.
        """
        # Resolve the winning filing first — keeps the holdings query
        # parameterised on a single filing_id which the
        # ix_f13_holdings_filing_id index covers exactly.
        filing_row = await self.db.execute(
            select(F13Filing.id)
            .where(
                F13Filing.filer_id == filer_id,
                F13Filing.report_period_end == report_period_end,
            )
            .order_by(desc(F13Filing.filed_at))
            .limit(1)
        )
        filing_id = filing_row.scalar_one_or_none()
        if filing_id is None:
            return []
        return await self.list_by_filing(filing_id)

    async def list_by_stock(
        self, stock_id: int, limit: int = 50
    ) -> list[tuple[F13Holding, F13Filing, F13Filer]]:
        """Per-stock institutional view — Pro tier backing query.

        Returns the most recent holdings rows for `stock_id`, joined to
        filing + filer metadata so the panel can render
        `(filer_name, period, shares, value)` triples without N+1.

        Order: by filing date DESC so the freshest position per filer
        bubbles up first. Service layer is expected to apply final
        grouping (one row per filer = the latest position).
        """
        result = await self.db.execute(
            select(F13Holding, F13Filing, F13Filer)
            .join(F13Filing, F13Filing.id == F13Holding.filing_id)
            .join(F13Filer, F13Filer.id == F13Filing.filer_id)
            .where(F13Holding.stock_id == stock_id)
            .order_by(
                desc(F13Filing.report_period_end),
                F13Filer.name.asc(),
            )
            .limit(limit)
        )
        return [(h, f, fl) for h, f, fl in result.all()]

    async def list_by_cusip(
        self, cusip: str, limit: int = 50
    ) -> list[tuple[F13Holding, F13Filing, F13Filer]]:
        """Same shape as `list_by_stock` but keyed by raw CUSIP.

        Needed for the case where the user landed on an unmapped stock
        (no `stocks.cusip` row yet). The 13F holding row still carries
        CUSIP so we can render the cross-filer view from CUSIP alone.
        """
        result = await self.db.execute(
            select(F13Holding, F13Filing, F13Filer)
            .join(F13Filing, F13Filing.id == F13Holding.filing_id)
            .join(F13Filer, F13Filer.id == F13Filing.filer_id)
            .where(F13Holding.cusip == cusip)
            .order_by(
                desc(F13Filing.report_period_end),
                F13Filer.name.asc(),
            )
            .limit(limit)
        )
        return [(h, f, fl) for h, f, fl in result.all()]
