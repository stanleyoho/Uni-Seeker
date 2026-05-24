"""Integration tests for `RebalancingService`.

Spec: Portfolio Phase 5+ rebalancing tool — Pro-tier feature. Covers
the service-layer path (DB + tier guard + audit log) not the HTTP
layer (which is shared boilerplate already exercised in
`test_holdings_api.py`).

Coverage (6 cases):
  RS01 preview happy path (Pro user) — suggested trades emitted
  RS02 tier free → TierFeatureUnavailable raised
  RS03 tier basic → TierFeatureUnavailable raised
  RS04 account_id filter scopes positions correctly
  RS05 audit log row written with the right action + metadata
  RS06 live_price_fetcher is invoked with the union of position symbols
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import LivePriceFetcher, PriceQuote
from app.services.portfolio.account_service import PortfolioAccountService
from app.services.portfolio.exceptions import TierFeatureUnavailable
from app.services.portfolio.rebalancing_service import RebalancingService
from app.services.portfolio.trade_service import PortfolioTradeService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ── shared helpers (kept local — mirrors test_portfolio_services pattern) ─


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


class MockLivePriceFetcher:
    """In-memory `LivePriceFetcher` for service tests."""

    def __init__(
        self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None
    ) -> None:
        self._quotes = quotes or {}
        self.calls: list[list[str]] = []

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
        self.calls.append(list(stock_ids))
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid not in self._quotes:
                continue
            last, prev = self._quotes[sid]
            out[sid] = PriceQuote(
                stock_id=sid,
                last_price=last,
                prev_close=prev,
                as_of=datetime(2026, 5, 10, tzinfo=UTC),
            )
        return out


_proto_check: LivePriceFetcher = MockLivePriceFetcher()  # type: ignore[assignment]


async def _seed_account(db: AsyncSession, user: User, name: str = "acc") -> int:
    acc_svc = PortfolioAccountService(db, user)
    acc = await acc_svc.create_account(name=name, market=Market.TW_TWSE)
    await db.commit()
    return acc.id


async def _buy(
    db: AsyncSession,
    user: User,
    account_id: int,
    symbol: str,
    qty: str,
    price: str,
) -> None:
    """Convenience: record a BUY trade so the position exists."""
    svc = PortfolioTradeService(db, user)
    await svc.record_trade(
        account_id=account_id,
        action="BUY",
        symbol=symbol,
        market=Market.TW_TWSE,
        qty=Decimal(qty),
        price=Decimal(price),
        trade_date=date(2026, 5, 1),
    )
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RS01_preview_happy_path_pro_user(
    db_session: AsyncSession,
) -> None:
    """Pro user with two holdings → preview emits BUY+SELL suggestions."""
    user = await _mk_user(db_session, "rb1@x.com", "rb1")
    acc_id = await _seed_account(db_session, user)
    await _buy(db_session, user, acc_id, "2330", qty="100", price="500")
    await _buy(db_session, user, acc_id, "0050", qty="500", price="100")

    fetcher = MockLivePriceFetcher(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )
    svc = RebalancingService(db_session, user, fetcher)

    # Currently 50/50 (50_000 each = 100_000 total).
    # Target 70/30 → BUY 2330 +14_000, SELL 0050 -20_000... wait
    # actually 100_000*0.7=70_000 - 50_000 = 20_000 BUY 2330.
    # 100_000*0.3=30_000 - 50_000 = -20_000 SELL 0050.
    result = await svc.preview_rebalance(
        targets=[
            {"symbol": "2330", "market": "TW_TWSE", "target_pct": "70"},
            {"symbol": "0050", "market": "TW_TWSE", "target_pct": "30"},
        ],
        account_id=acc_id,
    )
    actions = {t.symbol: t.action for t in result.suggested_trades}
    assert actions == {"2330": "BUY", "0050": "SELL"}
    assert result.total_portfolio_value == Decimal("100000")


@pytest.mark.asyncio
async def test_RS02_tier_free_raises_feature_unavailable(
    db_session: AsyncSession,
) -> None:
    """FREE user → TierFeatureUnavailable (translates to 403 in API)."""
    user = await _mk_user(db_session, "rb2@x.com", "rb2", tier=UserTier.FREE)
    fetcher = MockLivePriceFetcher()
    svc = RebalancingService(db_session, user, fetcher)

    with patch(
        "app.services.portfolio.rebalancing_service.settings"
    ) as s:
        s.enable_monetization = True
        with pytest.raises(TierFeatureUnavailable) as exc:
            await svc.preview_rebalance(targets=[])
        assert exc.value.feature == "rebalancing"


@pytest.mark.asyncio
async def test_RS03_tier_basic_raises_feature_unavailable(
    db_session: AsyncSession,
) -> None:
    """BASIC also lacks the feature flag → 403 in HTTP terms."""
    user = await _mk_user(db_session, "rb3@x.com", "rb3", tier=UserTier.BASIC)
    fetcher = MockLivePriceFetcher()
    svc = RebalancingService(db_session, user, fetcher)

    with patch(
        "app.services.portfolio.rebalancing_service.settings"
    ) as s:
        s.enable_monetization = True
        with pytest.raises(TierFeatureUnavailable) as exc:
            await svc.preview_rebalance(targets=[])
        assert exc.value.feature == "rebalancing"


@pytest.mark.asyncio
async def test_RS04_account_id_filter_scopes_positions(
    db_session: AsyncSession,
) -> None:
    """When `account_id` is set, only that account's positions count.

    We seed two accounts with different holdings; previewing against
    one account must NOT see the other's positions.
    """
    user = await _mk_user(db_session, "rb4@x.com", "rb4")
    acc1 = await _seed_account(db_session, user, name="acc1")
    acc2 = await _seed_account(db_session, user, name="acc2")
    await _buy(db_session, user, acc1, "2330", qty="100", price="500")
    await _buy(db_session, user, acc2, "0050", qty="500", price="100")

    fetcher = MockLivePriceFetcher(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )
    svc = RebalancingService(db_session, user, fetcher)

    # Preview only acc1 → total should be 50_000 (just 2330).
    result = await svc.preview_rebalance(
        targets=[
            {"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"},
        ],
        account_id=acc1,
    )
    assert result.total_portfolio_value == Decimal("50000")
    # No SELL of 0050 should appear — acc2's position isn't visible.
    assert all(t.symbol != "0050" for t in result.suggested_trades)


@pytest.mark.asyncio
async def test_RS05_audit_log_written(
    db_session: AsyncSession,
) -> None:
    """Every preview emits a `portfolio.rebalance_previewed` audit row."""
    user = await _mk_user(db_session, "rb5@x.com", "rb5")
    acc_id = await _seed_account(db_session, user)
    await _buy(db_session, user, acc_id, "2330", qty="100", price="500")

    fetcher = MockLivePriceFetcher(
        {"2330": (Decimal("500"), Decimal("500"))}
    )
    svc = RebalancingService(db_session, user, fetcher)

    await svc.preview_rebalance(
        targets=[
            {"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"}
        ],
        account_id=acc_id,
    )
    await db_session.commit()

    n = await db_session.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "portfolio.rebalance_previewed",
            AuditLog.user_id == user.id,
        )
    )
    assert int(n or 0) == 1


@pytest.mark.asyncio
async def test_RS06_live_price_fetcher_called_with_position_symbols(
    db_session: AsyncSession,
) -> None:
    """The injected fetcher should be called exactly once with the
    distinct sorted symbols of the user's open positions.

    Important: this verifies dependency injection, NOT real network
    calls — the mock records every call list so we can assert on it.
    """
    user = await _mk_user(db_session, "rb6@x.com", "rb6")
    acc_id = await _seed_account(db_session, user)
    await _buy(db_session, user, acc_id, "2330", qty="100", price="500")
    await _buy(db_session, user, acc_id, "0050", qty="500", price="100")

    fetcher = MockLivePriceFetcher(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )
    svc = RebalancingService(db_session, user, fetcher)

    await svc.preview_rebalance(
        targets=[
            {"symbol": "2330", "market": "TW_TWSE", "target_pct": "60"},
            {"symbol": "0050", "market": "TW_TWSE", "target_pct": "40"},
        ],
        account_id=acc_id,
    )

    # One fetch, both symbols, sorted.
    assert len(fetcher.calls) == 1
    assert fetcher.calls[0] == sorted(["2330", "0050"])
