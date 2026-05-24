"""F13FilerSearchService — local + EDGAR-augmented filer search.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§6.2, §10 Q4 (filer search interface).

Search strategy (Phase 1 pragmatic compromise per Q4):
  1. Look locally in `f13_filers` first — instant, no rate limit.
  2. If fewer than `LOCAL_HIT_THRESHOLD` results, augment with
     EDGAR full-text search. The augmentation is best-effort:
     transient EDGAR failures degrade to "local-only" rather than
     raising.

Output shape is a list of dicts (not ORM rows) because EDGAR
contributions are not persisted yet — we don't want to leak a half-
filled `F13Filer` row to the caller. Subscribing later will create the
row idempotently via `F13SubscriptionService.subscribe(cik=...)`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.modules.institutional.edgar_client import (
    EdgarClient,
    EdgarTransientError,
)
from app.repositories.institutional import F13FilerRepo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = structlog.get_logger(__name__)

# When the local DB returns this many hits or more, skip EDGAR — local
# rows are good enough and we save a 500ms+ round trip. Set to a small
# number for Phase 1 because the f13_filers table starts near-empty.
LOCAL_HIT_THRESHOLD = 5


class F13FilerSearchService:
    """Search filers by name across local DB + EDGAR full-text index.

    Service takes the EdgarClient as a constructor arg so tests can
    inject a mock — the client is also responsible for its own httpx
    lifecycle (it's an async context manager). Pass an opened client.
    """

    def __init__(
        self,
        db: AsyncSession,
        user: User,
        edgar_client: EdgarClient,
    ) -> None:
        self._db = db
        self._user = user
        self._filer_repo = F13FilerRepo(db)
        self._edgar = edgar_client

    async def search_filers(
        self, query: str, limit: int = 20
    ) -> list[dict]:
        """Returns a list of `{cik, name, legal_name, is_locally_known}`.

        Args:
            query: free-text name search.
            limit: cap on the merged result list.

        Behaviour:
          - Local hits always appear first (sorted by name ASC).
          - EDGAR hits backfill up to `limit`, skipping CIKs already
            present in the local result.
          - An EDGAR failure logs a warning and returns the local-only
            list — never raises from this method. Search is a
            non-critical surface; degradation is preferable.
        """
        if not query or not query.strip():
            return []

        # --- local layer -----------------------------------------------
        local_rows = await self._filer_repo.search_by_name(query, limit=limit)
        local_ciks: set[str] = {row.cik for row in local_rows}
        merged: list[dict] = [
            {
                "cik": row.cik,
                "name": row.name,
                "legal_name": row.legal_name,
                "is_locally_known": True,
            }
            for row in local_rows
        ]

        # Skip EDGAR augmentation when we already have enough.
        if len(merged) >= LOCAL_HIT_THRESHOLD or len(merged) >= limit:
            return merged

        # --- EDGAR augmentation (best-effort) ---------------------------
        try:
            edgar_hits = await self._edgar.search_filers_by_name(
                query, limit=limit
            )
        except EdgarTransientError as exc:
            logger.warning(
                "f13_filer_search_edgar_unavailable",
                query=query,
                error=str(exc),
            )
            return merged
        except Exception as exc:
            logger.warning(
                "f13_filer_search_edgar_failed",
                query=query,
                error=str(exc),
            )
            return merged

        for hit in edgar_hits:
            if hit.cik in local_ciks:
                continue
            merged.append(
                {
                    "cik": hit.cik,
                    "name": hit.name,
                    "legal_name": hit.legal_name,
                    "is_locally_known": False,
                }
            )
            if len(merged) >= limit:
                break
        return merged
