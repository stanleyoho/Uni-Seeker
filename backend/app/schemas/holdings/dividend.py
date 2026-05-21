"""Dividend DTOs for /api/v1/holdings/dividends.

Spec §5.4 Table 3 + §6.2 Table 3 (Phase 2 Batch C). Mirrors the trade
DTO conventions:

- Decimal-as-string on the wire via `@field_serializer(..., when_used='json')`
  (see package docstring on `app.schemas.holdings`). The legacy
  `json_encoders` knob is deprecated in Pydantic 2.x and removed in v3.
- `from_attributes=True` on the response model so we can hand an ORM row
  to `DividendResponse.model_validate(row)` directly.

Phase 2 MVP behavioural notes (mirror service-layer docstring on
`PortfolioDividendService.update_dividend`):

- `DividendUpdateRequest` declares every field optional, but only `note`,
  `pay_date`, and `withholding_tax` are actually mutable by the service.
  Other keys raise `ValueError` in the service and translate to 422 in
  the API layer. We keep the wider DTO surface for forward-compat with
  Phase 3 when amount / ratio PATCH lands.
- `total_amount` / `net_amount` are NOT stored on the ORM row (see
  `app.db.models.portfolio.dividend` docstring) — they are re-derived
  here so the wire payload still carries the gross + net figures the
  frontend expects to render.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer

from app.models.enums import Market

DividendType = Literal["CASH", "STOCK"]


# ── request DTOs ────────────────────────────────────────────────────────────


class DividendCreateRequest(BaseModel):
    """POST /holdings/dividends body.

    CASH branch needs `amount_per_share`; STOCK branch needs `ratio`.
    The service layer enforces the mutually-exclusive rules and raises
    `ValueError` (→ 422) when violated — we deliberately keep both
    fields optional here so the API surface mirrors the service's
    permissive signature (one DTO covers both dividend types).
    """

    account_id: int
    symbol: str = Field(..., min_length=1, max_length=20)
    market: Market
    dividend_type: DividendType
    ex_dividend_date: date
    pay_date: date | None = None
    amount_per_share: Decimal | None = Field(default=None, gt=Decimal("0"))
    quantity_at_record: Decimal = Field(..., gt=Decimal("0"))
    ratio: Decimal | None = Field(default=None, gt=Decimal("0"))
    currency: str = Field(default="TWD", min_length=1, max_length=10)
    withholding_tax: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    note: str | None = None


class DividendUpdateRequest(BaseModel):
    """PATCH /holdings/dividends/{id} body — every field optional.

    Phase 2 MVP: only `note`, `pay_date`, `withholding_tax` are actually
    applied by `PortfolioDividendService.update_dividend`. Other fields
    are documented as forward-compat and rejected at the service layer
    with a `ValueError` that the API translates to 422.
    """

    note: str | None = None
    pay_date: date | None = None
    withholding_tax: Decimal | None = Field(default=None, ge=Decimal("0"))
    # Forward-compat shape (rejected by service in Phase 2):
    amount_per_share: Decimal | None = Field(default=None, gt=Decimal("0"))
    quantity_at_record: Decimal | None = Field(default=None, gt=Decimal("0"))
    ratio: Decimal | None = Field(default=None, gt=Decimal("0"))
    dividend_type: DividendType | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    market: Market | None = None
    ex_dividend_date: date | None = None
    currency: str | None = Field(default=None, min_length=1, max_length=10)


# ── response DTO ────────────────────────────────────────────────────────────


class DividendResponse(BaseModel):
    """Dividend row as exposed by GET / POST / PATCH on /holdings/dividends.

    `total_amount` and `net_amount` are computed (not stored) — see the
    ORM model docstring for the SQLite/Postgres parity rationale.

    For STOCK dividends, `amount_per_share` carries the ratio value
    (see service docstring); the human-readable ratio is also appended
    to `note` so the frontend can display it without parsing.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    market: Market
    dividend_type: str
    ex_dividend_date: date
    pay_date: date | None
    amount_per_share: Decimal
    quantity_at_record: Decimal
    currency: str
    withholding_tax: Decimal
    note: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "amount_per_share",
        "quantity_at_record",
        "withholding_tax",
        "total_amount",
        "net_amount",
        when_used="json",
    )
    def _serialize_decimal(self, value: Decimal) -> str:
        """Render Decimal as exact string on the wire (CLAUDE.md line 35).

        Replaces the deprecated `json_encoders={Decimal: str}` knob —
        scheduled for removal in Pydantic v3. Covers stored Decimal
        columns plus the two `@computed_field` properties below.
        """
        return str(value)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_amount(self) -> Decimal:
        """Gross dividend = amount_per_share × quantity_at_record.

        For STOCK dividends this is the gross *ratio × qty* figure — not
        a monetary value. The frontend disambiguates on `dividend_type`.
        """
        return Decimal(self.amount_per_share) * Decimal(self.quantity_at_record)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def net_amount(self) -> Decimal:
        """Net dividend = total_amount − withholding_tax.

        STOCK dividends record `withholding_tax=0` so net == total there.
        """
        return self.total_amount - Decimal(self.withholding_tax)


__all__ = [
    "DividendType",
    "DividendCreateRequest",
    "DividendUpdateRequest",
    "DividendResponse",
]


# Silence "unused import" for Any when pydantic adds future hooks.
_ = Any
