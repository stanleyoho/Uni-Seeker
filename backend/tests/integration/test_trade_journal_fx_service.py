"""Integration tests for `app.modules.trade_journal.fx_service.get_rate`.

Pure DB lookup module (not the cached `app.services.portfolio.fx_service`).
Covers: identity short-circuit, exact-date hit, fallback to most recent
past date, missing rate raises FXRateNotFoundError.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.journal import FXRate
from app.modules.trade_journal.fx_service import FXRateNotFoundError, get_rate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def test_get_rate_same_currency_returns_one(db_session: AsyncSession) -> None:
    """No conversion needed → return 1 without touching DB."""
    r = await get_rate(db_session, "TWD", "TWD")
    assert r == Decimal("1")


async def test_get_rate_returns_most_recent_match(db_session: AsyncSession) -> None:
    """Most recent date wins when multiple exist for the same pair."""
    db_session.add(
        FXRate(date=date(2026, 1, 1), from_currency="USD", to_currency="TWD", rate=Decimal("30.0"))
    )
    db_session.add(
        FXRate(date=date(2026, 3, 1), from_currency="USD", to_currency="TWD", rate=Decimal("31.5"))
    )
    db_session.add(
        FXRate(date=date(2026, 2, 1), from_currency="USD", to_currency="TWD", rate=Decimal("30.5"))
    )
    await db_session.commit()

    r = await get_rate(db_session, "USD", "TWD")
    assert r == Decimal("31.5")


async def test_get_rate_default_to_twd(db_session: AsyncSession) -> None:
    """to_currency defaults to TWD when omitted."""
    db_session.add(
        FXRate(date=date(2026, 1, 1), from_currency="USD", to_currency="TWD", rate=Decimal("30.0"))
    )
    await db_session.commit()

    r = await get_rate(db_session, "USD")
    assert r == Decimal("30.0")


async def test_get_rate_unknown_pair_raises(db_session: AsyncSession) -> None:
    """No rate at all for the requested pair → FXRateNotFoundError."""
    with pytest.raises(FXRateNotFoundError, match="USD→JPY"):
        await get_rate(db_session, "USD", "JPY")


async def test_get_rate_distinct_pairs_dont_cross_pollute(
    db_session: AsyncSession,
) -> None:
    """USD→TWD lookup must not return EUR→TWD even if EUR row is more recent."""
    db_session.add(
        FXRate(date=date(2026, 1, 1), from_currency="USD", to_currency="TWD", rate=Decimal("30.0"))
    )
    db_session.add(
        FXRate(
            date=date(2026, 5, 1),
            from_currency="EUR",
            to_currency="TWD",
            rate=Decimal("33.5"),
        )
    )
    await db_session.commit()

    assert await get_rate(db_session, "USD", "TWD") == Decimal("30.0")
    assert await get_rate(db_session, "EUR", "TWD") == Decimal("33.5")
