"""Filer DTOs — /api/v1/institutional/filers.

Spec §5 + §6.6. `F13FilerResponse` mirrors the denormalised hot-path
columns on `f13_filers` so dashboard cards can render without a JOIN
(see `F13Filer.latest_*` ORM fields). Decimal fields are emitted as
JSON strings per CLAUDE.md Decimal-as-string contract.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class F13FilerResponse(BaseModel):
    """One filer row as returned by `GET /institutional/filers/{filer_id}`
    and the list/subscription endpoints.

    `latest_total_value_usd` is the pure-long 13F market value (Q3
    decision) and `latest_options_notional_usd` is the put/call notional
    — both nullable until the first refresh ingests a filing for the
    filer.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    cik: str
    name: str
    legal_name: str | None
    latest_total_value_usd: Decimal | None
    latest_options_notional_usd: Decimal | None
    latest_filing_date: date | None
    latest_position_count: int | None
    created_at: datetime

    @field_serializer(
        "latest_total_value_usd",
        "latest_options_notional_usd",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        """Decimal-as-string per CLAUDE.md. `None` stays JSON null."""
        return None if value is None else str(value)


class F13FilerSearchResult(BaseModel):
    """One hit from `POST /institutional/filers/search`.

    `is_locally_known` distinguishes filers we already have a row for
    (instant subscribe) from EDGAR-only hits (subscribing will create
    the row on demand).
    """

    cik: str
    name: str
    legal_name: str | None
    is_locally_known: bool
