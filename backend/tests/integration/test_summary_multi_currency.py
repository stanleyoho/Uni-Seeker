"""Integration tests for `PortfolioSummaryService.get_user_summary_multi_currency`.

Spec: docs/superpowers/plans/2026-05-20-portfolio-tracker-design.md §11
      (Phase 4+ FX support).

Asserts:
  - cross-currency aggregation math (USD + JPY → TWD)
  - tier gate (multi_currency_summary only on Pro when >1 currency present)
  - single-currency fast path (no FX calls, no tier check)
  - empty portfolio short-circuit
  - rate snapshot exposed for transparency
  - missing-rate failure propagates as FxRateUnavailable
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from app.models.enums import Market, UserTier
from app.models.user import User
from app.modules.portfolio.fx_fetcher import FxFetchError, YFinanceFxFetcher
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher, PriceQuote
from app.repositories.portfolio import PortfolioAccountRepo, PortfolioPositionRepo
from app.services.portfolio import PortfolioSummaryService
from app.services.portfolio.exceptions import TierFeatureUnavailable
from app.services.portfolio.fx_service import FxRateUnavailable, FxService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── helpers ──────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    email: str,
    username: str,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


class _MockLPF:
    """Deterministic live price fetcher for summary tests."""

    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]]):
        self._q = quotes

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid not in self._q:
                continue
            last, prev = self._q[sid]
            out[sid] = PriceQuote(
                stock_id=sid,
                last_price=last,
                prev_close=prev,
                as_of=datetime(2026, 5, 19, tzinfo=UTC),
            )
        return out


# Protocol satisfaction check.
_ok: LivePriceFetcher = _MockLPF({})  # type: ignore[assignment]


class _MockFx(YFinanceFxFetcher):
    """Deterministic FX fetcher for summary tests."""

    def __init__(
        self,
        rates: dict[tuple[str, str], Decimal] | None = None,
        fail_pairs: set[tuple[str, str]] | None = None,
    ):
        super().__init__(ttl_seconds=60)
        self._rates = rates or {}
        self._fail = fail_pairs or set()

    async def fetch_rate(self, base: str, quote: str, as_of=None) -> Decimal:
        if base == quote:
            return Decimal("1")
        if (base, quote) in self._fail:
            raise FxFetchError(f"mock fail {base}/{quote}")
        if (base, quote) in self._rates:
            return self._rates[(base, quote)]
        raise FxFetchError(f"no rate {base}/{quote}")


async def _seed_account_and_position(
    db: AsyncSession,
    user: User,
    *,
    account_name: str,
    account_currency: str,
    market: Market,
    symbol: str,
    qty: Decimal,
    avg_cost: Decimal,
) -> int:
    """Create one account + one position row with explicit currency."""
    repo = PortfolioAccountRepo(db)
    acc = await repo.create(
        user_id=user.id,
        name=account_name,
        market=market,
        broker=None,
        currency=account_currency,
        description=None,
    )
    await db.flush()

    pos_repo = PortfolioPositionRepo(db)
    await pos_repo.upsert(
        account_id=acc.id,
        symbol=symbol,
        market=market,
        currency=account_currency,
        quantity=qty,
        avg_cost=avg_cost,
        total_cost=avg_cost * qty,
    )
    await db.commit()
    return acc.id


# ── tests ────────────────────────────────────────────────────────────────


async def test_multi_currency_aggregates_usd_and_twd(
    db_session: AsyncSession,
) -> None:
    """USD bucket converts to TWD; totals match expected math."""
    user = await _mk_user(db_session, "mc1@x.com", "mc1", tier=UserTier.PRO)
    # 10 NVDA @ 100 USD (last 110), 100 2330 @ 500 TWD (last 600).
    await _seed_account_and_position(
        db_session,
        user,
        account_name="US",
        account_currency="USD",
        market=Market.US_NASDAQ,
        symbol="NVDA",
        qty=Decimal("10"),
        avg_cost=Decimal("100"),
    )
    await _seed_account_and_position(
        db_session,
        user,
        account_name="TW",
        account_currency="TWD",
        market=Market.TW_TWSE,
        symbol="2330",
        qty=Decimal("100"),
        avg_cost=Decimal("500"),
    )

    lpf = _MockLPF(
        {
            "NVDA": (Decimal("110"), Decimal("105")),
            "2330": (Decimal("600"), Decimal("590")),
        }
    )
    fx_fetcher = _MockFx(rates={("USD", "TWD"): Decimal("31")})
    fx_service = FxService(db_session, fx_fetcher)

    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = False
        result = await svc.get_user_summary_multi_currency(base_currency="TWD")

    # USD: cost=10*100=1000 USD, value=10*110=1100 USD → 31000 / 34100 TWD.
    # TWD: cost=100*500=50000, value=100*600=60000.
    # Total TWD: cost=81000, value=94100.
    assert result.base_currency == "TWD"
    assert result.summary.total_cost == Decimal("81000")
    assert result.summary.total_value == Decimal("94100")
    assert "USD" in result.by_currency_native
    assert "TWD" in result.by_currency_native
    assert result.rates_used["USD"] == Decimal("31")
    assert result.rates_used["TWD"] == Decimal("1")


async def test_multi_currency_tier_gate_blocks_free(
    db_session: AsyncSession,
) -> None:
    """FREE tier without multi_currency_summary → TierFeatureUnavailable
    when positions span >1 currency."""
    user = await _mk_user(db_session, "mc2@x.com", "mc2", tier=UserTier.FREE)
    await _seed_account_and_position(
        db_session,
        user,
        account_name="US",
        account_currency="USD",
        market=Market.US_NASDAQ,
        symbol="NVDA",
        qty=Decimal("5"),
        avg_cost=Decimal("100"),
    )
    await _seed_account_and_position(
        db_session,
        user,
        account_name="TW",
        account_currency="TWD",
        market=Market.TW_TWSE,
        symbol="2330",
        qty=Decimal("10"),
        avg_cost=Decimal("500"),
    )

    lpf = _MockLPF(
        {
            "NVDA": (Decimal("100"), Decimal("100")),
            "2330": (Decimal("500"), Decimal("500")),
        }
    )
    fx_service = FxService(db_session, _MockFx(rates={("USD", "TWD"): Decimal("31")}))
    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = True
        with pytest.raises(TierFeatureUnavailable) as exc:
            await svc.get_user_summary_multi_currency(base_currency="TWD")
        assert exc.value.feature == "multi_currency_summary"


async def test_multi_currency_single_ccy_no_tier_check(
    db_session: AsyncSession,
) -> None:
    """FREE tier with only one currency → does NOT trigger tier gate."""
    user = await _mk_user(db_session, "mc3@x.com", "mc3", tier=UserTier.FREE)
    await _seed_account_and_position(
        db_session,
        user,
        account_name="TW",
        account_currency="TWD",
        market=Market.TW_TWSE,
        symbol="2330",
        qty=Decimal("10"),
        avg_cost=Decimal("500"),
    )

    lpf = _MockLPF({"2330": (Decimal("600"), Decimal("590"))})
    fx_service = FxService(db_session, _MockFx())
    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = True
        result = await svc.get_user_summary_multi_currency(base_currency="TWD")

    # Single-currency fast path: 10 * 500 = 5000 cost, 10 * 600 = 6000 value.
    assert result.summary.total_cost == Decimal("5000")
    assert result.summary.total_value == Decimal("6000")
    assert set(result.by_currency_native.keys()) == {"TWD"}
    assert result.rates_used == {"TWD": Decimal("1")}


async def test_multi_currency_empty_portfolio_returns_zero(
    db_session: AsyncSession,
) -> None:
    """No positions → all-zero summary."""
    user = await _mk_user(db_session, "mc4@x.com", "mc4")
    lpf = _MockLPF({})
    fx_service = FxService(db_session, _MockFx())
    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = False
        result = await svc.get_user_summary_multi_currency(base_currency="TWD")

    assert result.summary.total_cost == Decimal("0")
    assert result.summary.total_value == Decimal("0")
    assert result.by_currency_native == {}


async def test_multi_currency_missing_rate_raises(
    db_session: AsyncSession,
) -> None:
    """If FX rate cannot be obtained → FxRateUnavailable propagates."""
    user = await _mk_user(db_session, "mc5@x.com", "mc5", tier=UserTier.PRO)
    await _seed_account_and_position(
        db_session,
        user,
        account_name="US",
        account_currency="USD",
        market=Market.US_NASDAQ,
        symbol="NVDA",
        qty=Decimal("5"),
        avg_cost=Decimal("100"),
    )
    await _seed_account_and_position(
        db_session,
        user,
        account_name="TW",
        account_currency="TWD",
        market=Market.TW_TWSE,
        symbol="2330",
        qty=Decimal("10"),
        avg_cost=Decimal("500"),
    )

    lpf = _MockLPF(
        {
            "NVDA": (Decimal("100"), Decimal("100")),
            "2330": (Decimal("500"), Decimal("500")),
        }
    )
    fx_service = FxService(
        db_session,
        _MockFx(fail_pairs={("USD", "TWD")}),
    )
    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = False
        with pytest.raises(FxRateUnavailable):
            await svc.get_user_summary_multi_currency(base_currency="TWD")


async def test_multi_currency_rates_used_exposed(
    db_session: AsyncSession,
) -> None:
    """`rates_used` snapshot covers every currency present (including base)."""
    user = await _mk_user(db_session, "mc6@x.com", "mc6", tier=UserTier.PRO)
    await _seed_account_and_position(
        db_session,
        user,
        account_name="JP",
        account_currency="JPY",
        market=Market.US_NASDAQ,  # market doesn't matter — currency does
        symbol="SONY",
        qty=Decimal("100"),
        avg_cost=Decimal("1500"),
    )
    await _seed_account_and_position(
        db_session,
        user,
        account_name="TW",
        account_currency="TWD",
        market=Market.TW_TWSE,
        symbol="2330",
        qty=Decimal("10"),
        avg_cost=Decimal("500"),
    )

    lpf = _MockLPF(
        {
            "SONY": (Decimal("1600"), Decimal("1550")),
            "2330": (Decimal("550"), Decimal("540")),
        }
    )
    fx_fetcher = _MockFx(rates={("JPY", "TWD"): Decimal("0.21")})
    fx_service = FxService(db_session, fx_fetcher)
    svc = PortfolioSummaryService(
        db_session,
        user,
        lpf,
        fx_service=fx_service,  # type: ignore[arg-type]
    )

    with patch("app.services.portfolio.summary_service.settings") as s:
        s.enable_monetization = False
        result = await svc.get_user_summary_multi_currency(base_currency="TWD")

    assert result.rates_used["JPY"] == Decimal("0.21")
    assert result.rates_used["TWD"] == Decimal("1")
    # JPY native: cost=100*1500=150000 JPY, value=100*1600=160000 JPY.
    # In TWD: 31500 / 33600.
    # TWD native: cost=5000, value=5500.
    # Total TWD: 36500 / 39100.
    assert result.summary.total_cost == Decimal("36500.00")
    assert result.summary.total_value == Decimal("39100.00")
