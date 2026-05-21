"""F13FilingRepo — CRUD over `f13_filings`.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§4.3 Table 3, §6.3.

`f13_filings` is a per-filer historical log. The natural sort order is
`report_period_end DESC` (the index `ix_f13_filings_filer_period_desc`
is engineered for that exact query).

Isolation: **NO `user_id` filter** here either — a filing belongs to a
filer, not a user. Access control is enforced at the service layer by
checking `subscription_repo.is_subscribed(user_id, filer_id)` first.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from app.db.models.institutional.filing import F13Filing

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class F13FilingRepo:
    """CRUD over `f13_filings`."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        filer_id: int,
        accession_number: str,
        form_type: str,
        report_period_end: date,
        filed_at: datetime,
        total_value_usd: Decimal,
        options_notional_usd: Decimal,
        total_positions: int,
        raw_xml_url: str,
    ) -> F13Filing:
        """Insert a filing row. Caller is expected to have called
        `exists()` first to short-circuit idempotent refreshes; the DB
        UNIQUE (filer_id, accession_number) is the safety net.
        """
        filing = F13Filing(
            filer_id=filer_id,
            accession_number=accession_number,
            form_type=form_type,
            report_period_end=report_period_end,
            filed_at=filed_at,
            total_value_usd=total_value_usd,
            options_notional_usd=options_notional_usd,
            total_positions=total_positions,
            raw_xml_url=raw_xml_url,
        )
        self.db.add(filing)
        await self.db.flush()
        await self.db.refresh(filing)
        return filing

    async def get_by_id(self, filing_id: int) -> F13Filing | None:
        result = await self.db.execute(
            select(F13Filing).where(F13Filing.id == filing_id)
        )
        return result.scalar_one_or_none()

    async def list_by_filer(
        self,
        filer_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[F13Filing]:
        """All filings for `filer_id`, newest period first.

        Spec §4.3 ordering — uses `ix_f13_filings_filer_period_desc`.
        """
        result = await self.db.execute(
            select(F13Filing)
            .where(F13Filing.filer_id == filer_id)
            .order_by(desc(F13Filing.report_period_end))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_latest_for_filer(
        self, filer_id: int
    ) -> F13Filing | None:
        """Most recent filing by `report_period_end` (DESC).

        Distinct from "latest by `filed_at`" — for an amendment
        (13F-HR/A) refiled months after the period, the period-end
        ordering wins because that is what the UI shows.
        """
        result = await self.db.execute(
            select(F13Filing)
            .where(F13Filing.filer_id == filer_id)
            .order_by(desc(F13Filing.report_period_end))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_at_period(
        self, filer_id: int, report_period_end: date
    ) -> F13Filing | None:
        """Exact period-end match — used by `compute_diff(from, to)`.

        When both 13F-HR and 13F-HR/A exist for the same period (spec
        §11 R6 amendments), the amendment is preferred because it has
        the more recent `filed_at`. We resolve that by ordering DESC
        on `filed_at` and taking the first row.
        """
        result = await self.db.execute(
            select(F13Filing)
            .where(
                F13Filing.filer_id == filer_id,
                F13Filing.report_period_end == report_period_end,
            )
            .order_by(desc(F13Filing.filed_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def exists(
        self, filer_id: int, accession_number: str
    ) -> bool:
        """Cheap UNIQUE-key probe for refresh idempotency."""
        result = await self.db.execute(
            select(F13Filing.id).where(
                F13Filing.filer_id == filer_id,
                F13Filing.accession_number == accession_number,
            )
        )
        return result.scalar_one_or_none() is not None
