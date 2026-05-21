"""Filing / holding / diff / refresh DTOs — /api/v1/institutional/filers/{id}.

Spec §5 + §7.2 (diff contract). Decimal-as-string serialisation per
CLAUDE.md is wired via `field_serializer(..., when_used="json")` on
every numeric field that can carry value.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class F13FilingResponse(BaseModel):
    """One row of `f13_filings` — the per-quarter snapshot meta.

    Both totals can be NULL until a refresh fills them in. `raw_xml_url`
    points at the infotable.xml on EDGAR and is mostly diagnostic.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filer_id: int
    accession_number: str
    form_type: str
    report_period_end: date
    filed_at: datetime
    total_value_usd: Decimal | None
    options_notional_usd: Decimal | None
    total_positions: int | None
    raw_xml_url: str | None

    @field_serializer(
        "total_value_usd",
        "options_notional_usd",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class F13HoldingResponse(BaseModel):
    """One row of `f13_holdings`.

    `stock_symbol` is denormalised from `stocks.symbol` when the CUSIP
    has been mapped (`stock_id` not null); otherwise null and the UI
    displays the raw CUSIP + `name_of_issuer`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    cusip: str
    name_of_issuer: str
    value_usd: Decimal
    shares: Decimal | None
    put_call: str | None
    investment_discretion: str | None
    stock_id: int | None
    stock_symbol: str | None = None

    @field_serializer(
        "value_usd",
        "shares",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class F13HoldingsAtPeriodResponse(BaseModel):
    """`GET /institutional/filers/{id}/holdings?period=...` envelope.

    Carries the resolved filing meta + every holding row so the
    frontend renders both summary KPIs and the line items in one round
    trip.
    """

    filing: F13FilingResponse
    holdings: list[F13HoldingResponse]


class F13HoldingChangeResponse(BaseModel):
    """One row of the QoQ diff response.

    `change_type` is the 5-way classification (NEW / EXITED /
    INCREASED / DECREASED / UNCHANGED). `prev_*` are null for NEW
    rows; `curr_*` are null for EXITED rows. `delta_pct` is null when
    either side is missing.
    """

    cusip: str
    name_of_issuer: str
    change_type: str
    prev_shares: Decimal | None
    curr_shares: Decimal | None
    delta_shares: Decimal
    delta_pct: Decimal | None
    prev_value_usd: Decimal | None
    curr_value_usd: Decimal | None
    delta_value_usd: Decimal

    @field_serializer(
        "prev_shares",
        "curr_shares",
        "delta_shares",
        "delta_pct",
        "prev_value_usd",
        "curr_value_usd",
        "delta_value_usd",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class F13DiffResponse(BaseModel):
    """`GET /institutional/filers/{id}/diff` envelope."""

    prev_period: date
    curr_period: date
    changes: list[F13HoldingChangeResponse]


class F13RefreshResponse(BaseModel):
    """`POST /institutional/filers/{id}/refresh` response.

    Both counts are zero on a no-op refresh (nothing new on EDGAR
    since last ingest).
    """

    filings_added: int
    holdings_added: int
