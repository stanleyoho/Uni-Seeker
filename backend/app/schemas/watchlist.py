"""Pydantic schemas for /api/v1/watchlist endpoints — WATCH-001 / Plan 4 T7.

Round 6 polish:
  - WatchlistItemResponse gains optional `stock_name` (from JOIN on stocks.name).
  - WatchlistBulkAddRequest / WatchlistBulkAddResponse added for the new
    POST /watchlist/bulk endpoint — partial-success semantics with
    explicit added / skipped_duplicates / errors lists.

The bulk endpoint is atomic at the *quota* level (tier pre-check rejects
the whole batch with 403 when over cap) but reports per-symbol issues
(unknown symbol, etc.) inside the 201 envelope so the caller can show
them in one pass instead of N round-trips.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    # Joined from stocks.name on the read path. Nullable because the JOIN
    # may technically miss (e.g. orphaned watchlist row after a stock row
    # gets deleted out-of-band). Callers should fall back to symbol when
    # this is None.
    stock_name: str | None = None
    created_at: str


# ── Bulk add (Round 6) ──────────────────────────────────────────────────────


class WatchlistBulkAddRequest(BaseModel):
    """Bulk-add up to 20 symbols in one request.

    Validation:
      - At least 1, at most 20 symbols per call. The upper bound exists to
        keep one transaction reasonable in size and to protect Free tier
        users from accidentally blowing past the 10-item cap with one big
        paste.
      - Each symbol must be 1-20 chars after stripping whitespace. We
        intentionally do NOT enforce uppercase here — the endpoint
        normalises symbols server-side (uppercased) so the wire shape
        stays forgiving for the migration flow.
    """

    symbols: list[str] = Field(..., min_length=1, max_length=20)


class WatchlistBulkAddError(BaseModel):
    """One per-symbol failure inside a bulk add response.

    `reason` is a snake_case identifier matching the single-symbol API:
      - `stock_not_found`     — unknown symbol in stocks table
      - `invalid_symbol`      — failed normalisation (empty / too long)
      - `internal_error`      — unexpected DB-level failure for this row
    """

    symbol: str
    reason: str


class WatchlistBulkAddResponse(BaseModel):
    """Envelope for POST /watchlist/bulk.

    Three disjoint lists, each tagged with the canonical symbol that the
    caller submitted (post-normalisation):
      - `added`              — newly inserted watchlist rows
      - `skipped_duplicates` — symbols that were already on the user's
                               watchlist (treated as success, not failure)
      - `errors`             — symbols we could not insert (404 or other)

    Quota errors (403 limit_exceeded:max_watchlist) are NOT returned in
    this envelope — they short-circuit the whole batch with an HTTPException
    BEFORE any row is inserted.
    """

    added: list[WatchlistItemResponse]
    skipped_duplicates: list[str]
    errors: list[WatchlistBulkAddError]
