"""Account-level request / response DTOs for /api/v1/holdings/accounts.

Spec §5.4 Table 1 + §6.2 Table 1. Decimal-as-string is not relevant
here (no Decimal columns on accounts) but we follow the
`from_attributes=True` convention so the service can hand us a
SQLAlchemy `PortfolioAccount` directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Market
from app.schemas._base import StrictModel


class AccountCreateRequest(StrictModel):
    """POST /holdings/accounts body.

    `market` is required because the materialised `portfolio_accounts`
    row carries the default market for the account's trades (spec §6.2
    Table 1: NOT NULL).
    """

    name: str = Field(..., min_length=1, max_length=100)
    market: Market
    broker: str | None = Field(default=None, max_length=50)
    currency: str = Field(default="TWD", min_length=1, max_length=10)
    description: str | None = None


class AccountUpdateRequest(StrictModel):
    """PATCH /holdings/accounts/{id} body — every field optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    market: Market | None = None
    broker: str | None = Field(default=None, max_length=50)
    currency: str | None = Field(default=None, min_length=1, max_length=10)
    description: str | None = None


class AccountResponse(BaseModel):
    """Account row as exposed by GET / POST / PATCH on /holdings/accounts."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    market: Market
    broker: str | None
    currency: str
    description: str | None
    created_at: datetime
