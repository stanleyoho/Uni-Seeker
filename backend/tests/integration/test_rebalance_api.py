"""HTTP integration tests for /api/v1/holdings/rebalance/{preview,execute}.

Spec: Portfolio Phase 5+ rebalancing tool — Pro-tier. The service layer
is already covered by `test_rebalancing_service.py`; this file pins the
HTTP contract (status codes, response shape, dep override behaviour).

Phase 2 adds the execute endpoint:
    POST /api/v1/holdings/rebalance/execute

Tests in this file (Phase 2 additions):
    RA01 happy path — Pro user, 2-stock 50/50 → execute writes 2 trades
    RA02 tier free → 403 feature_unavailable:rebalancing
    RA03 cross-user account_id → 404
    RA04 skip path — min_trade_value above delta → entry in `skipped`,
         no trade written
    RA05 missing account_id → 422 account_id_required_for_execute
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import PriceQuote

# ── Helpers (mirrors test_holdings_api.py — kept local for isolation) ──────


async def _mk_user(
    db: AsyncSession,
    email: str,
    username: str | None = None,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=username or email.split("@")[0],
    )
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {create_access_token(user.id, user.email)}"
        )
    }


class _MockLivePriceFetcher:
    """Same in-memory fetcher as test_holdings_api.py — duplicated so this
    file stays standalone (Phase 1 conventions: no test cross-imports)."""

    def __init__(
        self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None
    ) -> None:
        self._quotes = quotes or {}

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
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


def _client_app(client: AsyncClient):
    """Reach into the httpx AsyncClient's transport for the FastAPI app
    the `client` fixture wired up (NOT the module-level `app.main.app`)."""
    return client._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def mock_fetcher_factory(client: AsyncClient):
    """Yield a callable that installs `_MockLivePriceFetcher(quotes)` on
    the same FastAPI app instance the `client` fixture uses."""
    app = _client_app(client)

    def _setup(quotes: dict[str, tuple[Decimal, Decimal]]) -> None:
        app.dependency_overrides[get_live_price_fetcher] = (
            lambda: _MockLivePriceFetcher(quotes)
        )

    yield _setup
    app.dependency_overrides.pop(get_live_price_fetcher, None)


async def _create_account(
    client: AsyncClient, user: User, name: str = "broker"
) -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": name, "market": "TW_TWSE"},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _buy(
    client: AsyncClient,
    user: User,
    aid: int,
    symbol: str,
    qty: str,
    price: str,
) -> None:
    r = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": symbol,
            "market": "TW_TWSE",
            "qty": qty,
            "price": price,
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text


# ═══════════════════════════════════════════════════════════════════════════
# RA01 — happy path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA01_execute_happy_path_writes_two_trades(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """Pro user, 50/50 portfolio, target 70/30 → BUY 2330 + SELL 0050.

    Both trades land in `executed`; nothing in `skipped` or `failed`;
    the DB now has 4 trade rows (2 seed BUYs + 2 from rebalance).
    """
    user = await _mk_user(db_session, "rba1@x.tw")
    aid = await _create_account(client, user)
    await _buy(client, user, aid, "2330", qty="100", price="500")
    await _buy(client, user, aid, "0050", qty="500", price="100")
    mock_fetcher_factory(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )

    r = await client.post(
        "/api/v1/holdings/rebalance/execute",
        json={
            "targets": [
                {"symbol": "2330", "market": "TW_TWSE", "target_pct": "70"},
                {"symbol": "0050", "market": "TW_TWSE", "target_pct": "30"},
            ],
            "account_id": aid,
        },
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["executed"]) == 2
    assert body["skipped"] == []
    assert body["failed"] == []
    actions = {row["symbol"]: row["action"] for row in body["executed"]}
    assert actions == {"2330": "BUY", "0050": "SELL"}
    # Each executed row carries its newly-minted trade_id.
    for row in body["executed"]:
        assert isinstance(row["trade_id"], int)
        assert row["trade_id"] > 0
    # total_executed_value = 20_000 BUY + 20_000 SELL = 40_000
    assert Decimal(body["total_executed_value"]) == Decimal("40000")

    # Sanity: 4 trades persisted (2 seed + 2 from rebalance).
    from app.db.models.portfolio.trade import PortfolioTrade

    n = await db_session.scalar(
        select(func.count(PortfolioTrade.id)).where(
            PortfolioTrade.account_id == aid,
        )
    )
    assert int(n or 0) == 4


# ═══════════════════════════════════════════════════════════════════════════
# RA02 — tier guard (FREE → 403)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA02_execute_free_tier_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """FREE user hits the dep-layer tier_guard before any DB write."""
    user = await _mk_user(db_session, "rba2@x.tw", tier=UserTier.FREE)
    # No need to seed positions — tier_guard short-circuits.
    mock_fetcher_factory({})

    with patch(
        "app.modules.billing.tier_limits.settings"
    ) as s_tg, patch(
        "app.services.portfolio.rebalancing_service.settings"
    ) as s_svc:
        s_tg.enable_monetization = True
        s_svc.enable_monetization = True
        r = await client.post(
            "/api/v1/holdings/rebalance/execute",
            json={
                "targets": [
                    {
                        "symbol": "2330",
                        "market": "TW_TWSE",
                        "target_pct": "100",
                    }
                ],
                "account_id": 1,
            },
            headers=_auth(user),
        )
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:rebalancing"


# ═══════════════════════════════════════════════════════════════════════════
# RA03 — cross-user account ownership (→ 404)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA03_execute_cross_user_account_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """User B aiming at user A's account_id → 404, no leak."""
    a = await _mk_user(db_session, "rba3a@x.tw")
    b = await _mk_user(db_session, "rba3b@x.tw")
    aid_a = await _create_account(client, a)
    mock_fetcher_factory({})

    r = await client.post(
        "/api/v1/holdings/rebalance/execute",
        json={
            "targets": [
                {"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"}
            ],
            "account_id": aid_a,
        },
        headers=_auth(b),
    )
    assert r.status_code == 404, r.text
    assert r.json()["message"] == "portfolio_account_not_found"


# ═══════════════════════════════════════════════════════════════════════════
# RA04 — min_trade_value skip path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA04_execute_min_trade_value_marks_skipped(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """When the suggested delta falls below `min_trade_value`, the row
    lands in `skipped` and no trade is written.

    Portfolio: 50/50 on 100k. Target 51/49 → delta is 1_000 for each
    side. With `min_trade_value=5000` both rows skip.
    """
    user = await _mk_user(db_session, "rba4@x.tw")
    aid = await _create_account(client, user)
    await _buy(client, user, aid, "2330", qty="100", price="500")
    await _buy(client, user, aid, "0050", qty="500", price="100")
    mock_fetcher_factory(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )

    r = await client.post(
        "/api/v1/holdings/rebalance/execute",
        json={
            "targets": [
                {"symbol": "2330", "market": "TW_TWSE", "target_pct": "51"},
                {"symbol": "0050", "market": "TW_TWSE", "target_pct": "49"},
            ],
            "account_id": aid,
            "min_trade_value": "5000",
        },
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["executed"] == []
    assert body["failed"] == []
    assert len(body["skipped"]) == 2
    reasons = {row["reason"] for row in body["skipped"]}
    assert reasons == {"below_min_trade_value"}
    assert Decimal(body["total_executed_value"]) == Decimal("0")

    # Sanity: still only the 2 seed trades, no new rows.
    from app.db.models.portfolio.trade import PortfolioTrade

    n = await db_session.scalar(
        select(func.count(PortfolioTrade.id)).where(
            PortfolioTrade.account_id == aid,
        )
    )
    assert int(n or 0) == 2


# ═══════════════════════════════════════════════════════════════════════════
# RA05 — account_id required for execute
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA05_execute_without_account_id_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """Phase 2 requires `account_id` — without it we 422 explicitly."""
    user = await _mk_user(db_session, "rba5@x.tw")
    aid = await _create_account(client, user)
    await _buy(client, user, aid, "2330", qty="100", price="500")
    mock_fetcher_factory(
        {"2330": (Decimal("500"), Decimal("500"))}
    )

    r = await client.post(
        "/api/v1/holdings/rebalance/execute",
        json={
            "targets": [
                {"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"}
            ],
            # account_id deliberately omitted
        },
        headers=_auth(user),
    )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "account_id_required_for_execute"
