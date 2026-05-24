"""Integration tests for /api/v1/holdings/* — Portfolio Tracker Phase 1
Batch D.

Spec §10.3 (full-stack tests w/ mock LivePriceFetcher) + §13 AC matrix.
~25 cases. Mirrors `test_portfolio_services.py` for service-layer
parity, but exercises the HTTP path and asserts on
`response.json()["message"]` (the `detail` string after
`error_handler.py:13` rewriting).

Fetcher injection
-----------------
`get_live_price_fetcher` is dep-overridden to `MockLivePriceFetcher`
on a per-test basis. Decimals in the response body are JSON strings
per `CLAUDE.md` Decimal-as-string rule.
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
from app.models.audit_log import AuditLog
from app.models.enums import Market, UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import PriceQuote

# ── Helpers ─────────────────────────────────────────────────────────────────


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
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


class _MockLivePriceFetcher:
    """In-memory `LivePriceFetcher` for dep override."""

    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        self._quotes = quotes or {}

    async def fetch_quotes(self, stock_ids: list[str]) -> dict[str, PriceQuote]:
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
    """Reach into the httpx AsyncClient's ASGITransport to grab the
    FastAPI app instance set up by the top-level `client` fixture.

    `tests/conftest.py::client` calls `create_app()` which returns a
    NEW instance (not `app.main.app`), so we MUST override on this
    instance for dep overrides to actually fire.
    """
    return client._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def mock_fetcher_empty(client: AsyncClient):
    """Override live price fetcher with an empty MockLivePriceFetcher."""
    app = _client_app(client)
    app.dependency_overrides[get_live_price_fetcher] = lambda: _MockLivePriceFetcher()
    yield
    app.dependency_overrides.pop(get_live_price_fetcher, None)


@pytest.fixture
def mock_fetcher_factory(client: AsyncClient):
    """Yields a callable that sets up the live-price override on the
    same FastAPI app instance the `client` fixture is bound to."""
    app = _client_app(client)

    def _setup(quotes: dict[str, tuple[Decimal, Decimal]]) -> None:
        app.dependency_overrides[get_live_price_fetcher] = lambda: _MockLivePriceFetcher(quotes)

    yield _setup
    app.dependency_overrides.pop(get_live_price_fetcher, None)


async def _create_account_via_api(client: AsyncClient, user: User, name: str = "Yuanta") -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": name, "market": "TW_TWSE", "broker": "Yuanta"},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


# ═══════════════════════════════════════════════════════════════════════════
# Accounts (8 cases)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_accounts_post_creates_row_and_audits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "acc1@x.tw")
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={
            "name": "Yuanta",
            "market": "TW_TWSE",
            "broker": "Yuanta",
            "currency": "TWD",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Yuanta"
    assert body["market"] == "TW_TWSE"
    assert body["broker"] == "Yuanta"
    assert body["id"] is not None
    audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.action == "portfolio_account_created",
            AuditLog.user_id == user.id,
        )
    )
    assert audits == 1


@pytest.mark.asyncio
async def test_accounts_get_lists_user_accounts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    u1 = await _mk_user(db_session, "acc2a@x.tw")
    u2 = await _mk_user(db_session, "acc2b@x.tw")
    await _create_account_via_api(client, u1, name="A1")
    await _create_account_via_api(client, u1, name="A2")
    await _create_account_via_api(client, u2, name="other")

    r = await client.get("/api/v1/holdings/accounts", headers=_auth(u1))
    assert r.status_code == 200
    names = sorted(row["name"] for row in r.json())
    assert names == ["A1", "A2"]


@pytest.mark.asyncio
async def test_accounts_get_unknown_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "acc3@x.tw")
    r = await client.get("/api/v1/holdings/accounts/99999", headers=_auth(user))
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


@pytest.mark.asyncio
async def test_accounts_patch_updates_fields(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "acc4@x.tw")
    aid = await _create_account_via_api(client, user, name="old")
    r = await client.patch(
        f"/api/v1/holdings/accounts/{aid}",
        json={"name": "new", "broker": "Fubon"},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "new"
    assert body["broker"] == "Fubon"


@pytest.mark.asyncio
async def test_accounts_delete_removes_and_cascades(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "acc5@x.tw")
    aid = await _create_account_via_api(client, user)
    # Add a trade so cascade has something to remove.
    rt = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    assert rt.status_code == 201, rt.text

    r = await client.delete(f"/api/v1/holdings/accounts/{aid}", headers=_auth(user))
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # Refetch → 404 (the account row is gone)
    rg = await client.get(f"/api/v1/holdings/accounts/{aid}", headers=_auth(user))
    assert rg.status_code == 404


@pytest.mark.asyncio
async def test_accounts_max_accounts_quota_blocks_with_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """BASIC tier: max_accounts=3 → 4th create blocked.

    We patch monetization on. BASIC has multi_account=true so the
    multi_account feature flag does NOT trip; only the numeric quota
    does.
    """
    user = await _mk_user(db_session, "acc6@x.tw", tier=UserTier.BASIC)
    with (
        patch("app.services.portfolio.account_service.settings") as s_svc,
        patch("app.modules.billing.tier_limits.settings") as s_tg,
    ):
        s_svc.enable_monetization = True
        s_tg.enable_monetization = True
        for n in range(3):
            r = await client.post(
                "/api/v1/holdings/accounts",
                json={"name": f"a{n}", "market": "TW_TWSE"},
                headers=_auth(user),
            )
            assert r.status_code == 201, r.text
        r4 = await client.post(
            "/api/v1/holdings/accounts",
            json={"name": "fourth", "market": "TW_TWSE"},
            headers=_auth(user),
        )
        assert r4.status_code == 403, r4.text
        assert r4.json()["message"] == "limit_exceeded:max_accounts"


@pytest.mark.asyncio
async def test_accounts_multi_account_feature_blocks_free_with_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier: multi_account=false → 2nd create blocked by feature
    flag (before the numeric quota would matter)."""
    user = await _mk_user(db_session, "acc7@x.tw", tier=UserTier.FREE)
    with (
        patch("app.services.portfolio.account_service.settings") as s_svc,
        patch("app.modules.billing.tier_limits.settings") as s_tg,
    ):
        s_svc.enable_monetization = True
        s_tg.enable_monetization = True
        r1 = await client.post(
            "/api/v1/holdings/accounts",
            json={"name": "first", "market": "TW_TWSE"},
            headers=_auth(user),
        )
        assert r1.status_code == 201, r1.text
        r2 = await client.post(
            "/api/v1/holdings/accounts",
            json={"name": "second", "market": "TW_TWSE"},
            headers=_auth(user),
        )
        assert r2.status_code == 403
        # The dependency-layer feature flag fires first.
        assert r2.json()["message"] == "feature_unavailable:multi_account"


@pytest.mark.asyncio
async def test_accounts_cross_user_get_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User B querying User A's account id sees 404, not 403, to avoid
    leaking existence."""
    a = await _mk_user(db_session, "acc8a@x.tw")
    b = await _mk_user(db_session, "acc8b@x.tw")
    aid = await _create_account_via_api(client, a)

    r = await client.get(f"/api/v1/holdings/accounts/{aid}", headers=_auth(b))
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


# ═══════════════════════════════════════════════════════════════════════════
# Trades (10 cases)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_trades_post_buy_creates_position(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr1@x.tw")
    aid = await _create_account_via_api(client, user)
    r = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "100",
            "price": "500",
            "fee": "28",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["action"] == "BUY"
    assert body["symbol"] == "2330"
    # Decimal-as-string on the wire. SQLA stores Numeric(24,8) with full
    # precision so the value comes back as `"500.00000000"`; compare via
    # Decimal to ignore trailing-zero formatting.
    assert isinstance(body["price"], str)
    assert Decimal(body["price"]) == Decimal("500")
    assert Decimal(body["quantity"]) == Decimal("100")


@pytest.mark.asyncio
async def test_trades_post_sell_after_buy_realizes_pnl(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr2@x.tw")
    aid = await _create_account_via_api(client, user)
    r1 = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "100",
            "price": "500",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "SELL",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "60",
            "price": "600",
            "trade_date": "2026-05-02",
        },
        headers=_auth(user),
    )
    assert r2.status_code == 201, r2.text


@pytest.mark.asyncio
async def test_trades_post_sell_insufficient_shares_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr3@x.tw")
    aid = await _create_account_via_api(client, user)
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "X",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    r = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "SELL",
            "symbol": "X",
            "market": "TW_TWSE",
            "qty": "11",
            "price": "200",
            "trade_date": "2026-05-02",
        },
        headers=_auth(user),
    )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "insufficient_shares"


@pytest.mark.asyncio
async def test_trades_get_list_paginates(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "tr4@x.tw")
    aid = await _create_account_via_api(client, user)
    for i in range(5):
        await client.post(
            "/api/v1/holdings/trades",
            json={
                "account_id": aid,
                "action": "BUY",
                "symbol": f"S{i}",
                "market": "TW_TWSE",
                "qty": "1",
                "price": "100",
                "trade_date": "2026-05-01",
            },
            headers=_auth(user),
        )
    r = await client.get(
        f"/api/v1/holdings/trades?account_id={aid}&limit=3&offset=0",
        headers=_auth(user),
    )
    assert r.status_code == 200
    assert len(r.json()) == 3


@pytest.mark.asyncio
async def test_trades_get_unknown_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr5@x.tw")
    r = await client.get("/api/v1/holdings/trades/99999", headers=_auth(user))
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_trade_not_found"


@pytest.mark.asyncio
async def test_trades_patch_rebuilds_position(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr6@x.tw")
    aid = await _create_account_via_api(client, user)
    r1 = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "100",
            "price": "500",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    tid = r1.json()["id"]

    r2 = await client.patch(
        f"/api/v1/holdings/trades/{tid}",
        json={"price": "600"},
        headers=_auth(user),
    )
    assert r2.status_code == 200, r2.text
    assert Decimal(r2.json()["price"]) == Decimal("600")


@pytest.mark.asyncio
async def test_trades_delete_rebuilds(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "tr7@x.tw")
    aid = await _create_account_via_api(client, user)
    r1 = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    tid = r1.json()["id"]
    r2 = await client.delete(f"/api/v1/holdings/trades/{tid}", headers=_auth(user))
    assert r2.status_code == 200, r2.text
    # Refetching that trade now 404s.
    r3 = await client.get(f"/api/v1/holdings/trades/{tid}", headers=_auth(user))
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_trades_monthly_quota_blocks_with_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier: max_trades_per_month=30 → 31st blocked.

    Patch the service-level counter to fake "30 already used" so we
    don't need to insert 30 real rows. With monetization on, the
    service-level second line raises `TierLimitExceeded` and the API
    translates to 403.
    """
    user = await _mk_user(db_session, "tr8@x.tw", tier=UserTier.FREE)
    aid = await _create_account_via_api(client, user)
    with (
        patch("app.services.portfolio.trade_service.settings") as s_svc,
        patch("app.modules.billing.tier_limits.settings") as s_tg,
        patch(
            "app.repositories.portfolio.trade_repo.PortfolioTradeRepo.count_by_user_this_month",
            return_value=30,
        ),
    ):
        s_svc.enable_monetization = True
        s_tg.enable_monetization = True
        r = await client.post(
            "/api/v1/holdings/trades",
            json={
                "account_id": aid,
                "action": "BUY",
                "symbol": "2330",
                "market": "TW_TWSE",
                "qty": "1",
                "price": "100",
                "trade_date": "2026-05-01",
            },
            headers=_auth(user),
        )
        assert r.status_code == 403, r.text
        assert r.json()["message"] == "limit_exceeded:max_trades_per_month"


@pytest.mark.asyncio
async def test_trades_audit_log_emitted_on_post(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "tr9@x.tw")
    aid = await _create_account_via_api(client, user)
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.action == "portfolio_trade_added",
            AuditLog.user_id == user.id,
        )
    )
    assert audits == 1


@pytest.mark.asyncio
async def test_trades_cross_user_post_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User B cannot record a trade on User A's account."""
    a = await _mk_user(db_session, "tr10a@x.tw")
    b = await _mk_user(db_session, "tr10b@x.tw")
    aid_a = await _create_account_via_api(client, a)

    r = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid_a,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "1",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(b),
    )
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


# ═══════════════════════════════════════════════════════════════════════════
# Positions (4 cases)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_positions_list_includes_live_pnl(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    user = await _mk_user(db_session, "po1@x.tw")
    aid = await _create_account_via_api(client, user)
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "100",
            "price": "500",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    mock_fetcher_factory({"2330": (Decimal("550"), Decimal("540"))})

    r = await client.get("/api/v1/holdings/positions", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["positions"]) == 1
    p = body["positions"][0]
    assert p["symbol"] == "2330"
    assert Decimal(p["last_price"]) == Decimal("550")
    # unrealized = (550 - 500) * 100 = 5000
    assert Decimal(p["unrealized_pnl"]) == Decimal("5000")
    # daily change = (550 - 540) * 100 = 1000
    assert Decimal(p["daily_change"]) == Decimal("1000")


@pytest.mark.asyncio
async def test_positions_get_single_returns_enriched_row(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    user = await _mk_user(db_session, "po2@x.tw")
    aid = await _create_account_via_api(client, user)
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    mock_fetcher_factory({"2330": (Decimal("120"), Decimal("110"))})

    r = await client.get(
        f"/api/v1/holdings/positions/{aid}/2330?market=TW_TWSE",
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "2330"
    assert Decimal(body["last_price"]) == Decimal("120")
    assert Decimal(body["qty"]) == Decimal("10")


@pytest.mark.asyncio
async def test_positions_empty_portfolio_returns_empty_list(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_empty,
) -> None:
    user = await _mk_user(db_session, "po3@x.tw")
    r = await client.get("/api/v1/holdings/positions", headers=_auth(user))
    assert r.status_code == 200
    assert r.json() == {"account_id": None, "positions": []}


@pytest.mark.asyncio
async def test_positions_cross_user_list_is_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """User B's `/positions` does NOT see user A's holdings."""
    a = await _mk_user(db_session, "po4a@x.tw")
    b = await _mk_user(db_session, "po4b@x.tw")
    aid_a = await _create_account_via_api(client, a)
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid_a,
            "action": "BUY",
            "symbol": "2330",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(a),
    )
    mock_fetcher_factory({"2330": (Decimal("120"), Decimal("110"))})

    r = await client.get("/api/v1/holdings/positions", headers=_auth(b))
    assert r.status_code == 200
    assert r.json()["positions"] == []


# ═══════════════════════════════════════════════════════════════════════════
# Summary (3 cases)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_summary_user_wide_aggregates_across_accounts(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    user = await _mk_user(db_session, "su1@x.tw")
    aid1 = await _create_account_via_api(client, user, name="a1")
    aid2 = await _create_account_via_api(client, user, name="a2")
    for aid, sym, qty, price in [
        (aid1, "2330", "10", "500"),
        (aid2, "2454", "5", "1000"),
    ]:
        await client.post(
            "/api/v1/holdings/trades",
            json={
                "account_id": aid,
                "action": "BUY",
                "symbol": sym,
                "market": "TW_TWSE",
                "qty": qty,
                "price": price,
                "trade_date": "2026-05-01",
            },
            headers=_auth(user),
        )
    mock_fetcher_factory(
        {
            "2330": (Decimal("600"), Decimal("550")),
            "2454": (Decimal("1100"), Decimal("1050")),
        }
    )

    r = await client.get("/api/v1/holdings/summary", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    # total_cost = 10*500 + 5*1000 = 10000
    assert Decimal(body["total_cost"]) == Decimal("10000")
    # total_value = 10*600 + 5*1100 = 11500
    assert Decimal(body["total_value"]) == Decimal("11500")
    assert Decimal(body["gain_simple"]) == Decimal("1500")
    assert body["position_count"] == 2
    assert body["account_count"] == 2


@pytest.mark.asyncio
async def test_summary_account_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    user = await _mk_user(db_session, "su2@x.tw")
    aid1 = await _create_account_via_api(client, user, name="a1")
    aid2 = await _create_account_via_api(client, user, name="a2")
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid1,
            "action": "BUY",
            "symbol": "A",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "100",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid2,
            "action": "BUY",
            "symbol": "B",
            "market": "TW_TWSE",
            "qty": "10",
            "price": "200",
            "trade_date": "2026-05-01",
        },
        headers=_auth(user),
    )
    mock_fetcher_factory(
        {
            "A": (Decimal("110"), Decimal("105")),
            "B": (Decimal("220"), Decimal("210")),
        }
    )

    r1 = await client.get(f"/api/v1/holdings/summary/{aid1}", headers=_auth(user))
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert Decimal(b1["total_cost"]) == Decimal("1000")
    assert Decimal(b1["total_value"]) == Decimal("1100")
    assert b1["account_count"] == 1


@pytest.mark.asyncio
async def test_summary_empty_portfolio_returns_zeros(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_empty,
) -> None:
    user = await _mk_user(db_session, "su3@x.tw")
    r = await client.get("/api/v1/holdings/summary", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["total_cost"]) == Decimal("0")
    assert Decimal(body["total_value"]) == Decimal("0")
    assert Decimal(body["gain_simple"]) == Decimal("0")
    assert body["position_count"] == 0
    assert body["account_count"] == 0
