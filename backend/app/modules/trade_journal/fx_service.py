"""FX rate lookup with fallback to most recent available date."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import FXRate


class FXRateNotFoundError(Exception):
    """Raised when no FX rate exists for the requested currency pair."""


async def get_rate(
    db: AsyncSession,
    from_currency: str,
    to_currency: str = "TWD",
) -> Decimal:
    """Return most recent rate for from_currency→to_currency.

    Falls back to nearest past date if today's rate is not yet available.
    Raises FXRateNotFoundError if no rate exists at all.
    If from_currency == to_currency, returns 1 (no conversion needed).
    """
    if from_currency == to_currency:
        return Decimal("1")

    stmt = (
        select(FXRate.rate)
        .where(
            FXRate.from_currency == from_currency,
            FXRate.to_currency == to_currency,
        )
        .order_by(FXRate.date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise FXRateNotFoundError(
            f"No FX rate found for {from_currency}→{to_currency}"
        )
    return row
