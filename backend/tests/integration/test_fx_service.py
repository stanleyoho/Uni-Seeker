"""Integration tests for `FxService` — DB cache + mock fetcher.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11.

The mock fetcher records call counts so we can assert that DB cache hits
short-circuit before reaching it.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from app.models.journal import FXRate
from app.modules.portfolio.fx_fetcher import FxFetchError, YFinanceFxFetcher
from app.services.portfolio.fx_service import (
    FxRateUnavailable,
    FxService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _MockFxFetcher(YFinanceFxFetcher):
    """Test double — returns pre-canned rates without hitting yfinance.

    Inherits from YFinanceFxFetcher so the `FxService.__init__` type
    annotation is satisfied. Overrides `fetch_rate` directly (skipping
    cache + sync layer) since we want deterministic + counting behaviour.
    """

    def __init__(
        self,
        rates: dict[tuple[str, str], Decimal] | None = None,
        fail_pairs: set[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__(ttl_seconds=60)
        self._rates = rates or {}
        self._fail = fail_pairs or set()
        self.calls: list[tuple[str, str, date | None]] = []

    async def fetch_rate(
        self,
        base: str,
        quote: str,
        as_of: date | None = None,
    ) -> Decimal:
        self.calls.append((base, quote, as_of))
        if base == quote:
            return Decimal("1")
        if (base, quote) in self._fail:
            raise FxFetchError(f"mock failure {base}/{quote}")
        if (base, quote) in self._rates:
            return self._rates[(base, quote)]
        raise FxFetchError(f"no canned rate for {base}/{quote}")


async def test_fx_service_db_cache_hit_skips_fetcher(
    db_session: AsyncSession,
) -> None:
    """A row in `fx_rates` for today bypasses the fetcher entirely."""
    db_session.add(
        FXRate(
            date=date.today(),
            from_currency="USD",
            rate=Decimal("31.5"),
            to_currency="TWD",
        )
    )
    await db_session.commit()

    fetcher = _MockFxFetcher()
    svc = FxService(db_session, fetcher)
    rate = await svc.get_rate("USD", "TWD")

    assert rate == Decimal("31.5")
    assert fetcher.calls == []  # Cache hit — fetcher untouched.


async def test_fx_service_cache_miss_calls_fetcher_and_upserts(
    db_session: AsyncSession,
) -> None:
    """DB empty → calls fetcher → result is persisted for next call."""
    fetcher = _MockFxFetcher(
        rates={("USD", "TWD"): Decimal("31.0")},
    )
    svc = FxService(db_session, fetcher)
    rate = await svc.get_rate("USD", "TWD")
    await db_session.commit()

    assert rate == Decimal("31.0")
    assert len(fetcher.calls) == 1

    # Verify row was UPSERT'd.
    from sqlalchemy import select

    stmt = select(FXRate).where(
        FXRate.from_currency == "USD", FXRate.to_currency == "TWD"
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    assert rows[0].rate == Decimal("31.0")


async def test_fx_service_same_currency_short_circuit(
    db_session: AsyncSession,
) -> None:
    """`base == quote` returns 1 with no fetcher call, no DB row."""
    fetcher = _MockFxFetcher()
    svc = FxService(db_session, fetcher)
    rate = await svc.get_rate("TWD", "TWD")
    assert rate == Decimal("1")
    assert fetcher.calls == []


async def test_fx_service_unavailable_raises(
    db_session: AsyncSession,
) -> None:
    """Cache miss + fetcher failure → FxRateUnavailable."""
    fetcher = _MockFxFetcher(
        fail_pairs={("EUR", "TWD")},
    )
    svc = FxService(db_session, fetcher)
    with pytest.raises(FxRateUnavailable) as exc:
        await svc.get_rate("EUR", "TWD")
    assert exc.value.base == "EUR"
    assert exc.value.quote == "TWD"


async def test_fx_service_get_rates_for_currencies_batch(
    db_session: AsyncSession,
) -> None:
    """Batch helper returns rate=1 for self-pair and fetched rates otherwise."""
    fetcher = _MockFxFetcher(
        rates={
            ("USD", "TWD"): Decimal("31"),
            ("JPY", "TWD"): Decimal("0.21"),
        }
    )
    svc = FxService(db_session, fetcher)
    rates = await svc.get_rates_for_currencies(
        currencies={"USD", "JPY", "TWD"}, base="TWD"
    )
    assert rates == {
        "USD": Decimal("31"),
        "JPY": Decimal("0.21"),
        "TWD": Decimal("1"),
    }


async def test_fx_service_convert_amount(
    db_session: AsyncSession,
) -> None:
    """convert_amount = amount * get_rate."""
    fetcher = _MockFxFetcher(rates={("USD", "TWD"): Decimal("31")})
    svc = FxService(db_session, fetcher)
    out = await svc.convert_amount(Decimal("100"), "USD", "TWD")
    assert out == Decimal("3100")
