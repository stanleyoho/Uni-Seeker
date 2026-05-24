"""F13FilerRepo — CRUD over `f13_filers` (13F Holdings Tracker Phase 1).

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§4.3 Table 1, §6.3.

Isolation strategy — **NONE** by design (Q2 decision): the filer table
is a **shared resource**. Ten users tracking SALP share one row. The
user → filer relationship lives in `F13UserSubscriptionRepo` and that
is where structural `user_id` filters apply. A repo method here that
accidentally accepted a `user_id` would be a category error.

CRUD only — no business logic, no tier checks (spec §11 R3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.db.models.institutional.filer import F13Filer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class F13FilerRepo:
    """CRUD over `f13_filers`.

    `cik` is the canonical key (always 10-digit zero-padded — the
    EdgarClient already pads, callers should pass the same form). All
    methods flush but do not commit; the service layer owns the
    transaction boundary.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        cik: str,
        name: str,
        legal_name: str | None = None,
    ) -> F13Filer:
        """Insert a new filer row. Caller commits.

        Does NOT enforce uniqueness here — the DB UNIQUE on `cik` will
        reject duplicates. Use `get_or_create_by_cik` for idempotent
        callers (the refresh flow).
        """
        filer = F13Filer(cik=cik, name=name, legal_name=legal_name)
        self.db.add(filer)
        await self.db.flush()
        await self.db.refresh(filer)
        return filer

    async def get_by_id(self, filer_id: int) -> F13Filer | None:
        result = await self.db.execute(select(F13Filer).where(F13Filer.id == filer_id))
        return result.scalar_one_or_none()

    async def get_by_cik(self, cik: str) -> F13Filer | None:
        result = await self.db.execute(select(F13Filer).where(F13Filer.cik == cik))
        return result.scalar_one_or_none()

    async def search_by_name(self, q: str, limit: int = 20) -> list[F13Filer]:
        """Case-insensitive prefix-and-substring match on `name`.

        Phase 1 uses a vanilla `ILIKE %q%` — fast enough at our seed
        scale (low hundreds of filers). Spec §4.3 reserves an
        `ix_f13_filers_name_trgm` index for pg_trgm fuzzy search; that
        belongs to Phase 2 once the table grows.
        """
        if not q or not q.strip():
            return []
        pattern = f"%{q.strip()}%"
        result = await self.db.execute(
            select(F13Filer)
            .where(F13Filer.name.ilike(pattern))
            .order_by(F13Filer.name.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_latest_aum(
        self,
        filer_id: int,
        total_value_usd: Decimal,
        options_notional_usd: Decimal,
        position_count: int,
        filing_date: date,
    ) -> None:
        """Refresh the denormalised `latest_*` columns from the most recent
        filing. Called by `F13FilingService.refresh_filer` (Q3 two-column
        AUM contract).

        No-op when `filer_id` does not exist — callers are expected to
        verify existence beforehand. Returns nothing (caller doesn't
        need the row).
        """
        await self.db.execute(
            update(F13Filer)
            .where(F13Filer.id == filer_id)
            .values(
                latest_total_value_usd=total_value_usd,
                latest_options_notional_usd=options_notional_usd,
                latest_position_count=position_count,
                latest_filing_date=filing_date,
            )
        )
        await self.db.flush()

    async def get_or_create_by_cik(
        self,
        cik: str,
        name: str,
        legal_name: str | None = None,
    ) -> tuple[F13Filer, bool]:
        """Idempotent upsert by CIK.

        Returns `(filer, was_created)`. Race-safe under SQLite test
        sessions and Postgres because the UNIQUE constraint catches a
        concurrent inserter — we'd retry the SELECT on IntegrityError
        but Phase 1 only ever calls this from a single request scope
        (no background refresh contention).
        """
        existing = await self.get_by_cik(cik)
        if existing is not None:
            return existing, False
        created = await self.create(cik=cik, name=name, legal_name=legal_name)
        return created, True
