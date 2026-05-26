"""HTTP integration tests for /api/v1/holdings/rebalance/{preview,execute}.

Spec: Portfolio Phase 5+ rebalancing tool — Pro-tier. The service layer
is already covered by `test_rebalancing_service.py`; this file pins the
HTTP contract (status codes, response shape, dep override behaviour).

Phase 2 added the execute endpoint:
    POST /api/v1/holdings/rebalance/execute

Phase 3 (multi-account dispatch) loosens it: top-level ``account_id`` is
now optional. When omitted, each suggested trade routes to its source
position's ``account_id`` (multi-account aggregate execute). Brand-new
BUY symbols (no source position to derive from) make the aggregate plan
unroutable — surfaced as 422 ``account_unresolved_for_trade``.

Tests in this file:
    RA01 happy path — Pro user, 2-stock 50/50, single account → 2 trades
    RA02 tier free → 403 feature_unavailable:rebalancing
    RA03 cross-user account_id → 404
    RA04 skip path — min_trade_value above delta → entry in `skipped`
    RA05 aggregate mode, brand-new BUY → 422 account_unresolved_for_trade
         (renamed from Phase 2's account_id_required_for_execute)

Phase 3 additions:
    RA06 aggregate mode happy path — 2 accounts, each gets its own trade
    RA07 aggregate partial failure isolation — one account fails (live
         drift → InsufficientShares), other succeeds; both in response
    RA08 per-trade tier-limit halts the loop without writing remaining
    RA09 single-account back-compat — brand-new BUY with top-level
         account_id still executes (back-fills per-trade account_id)
    RA10 ownership defense-in-depth — planner-emitted account_id that
         the user doesn't own (stubbed via dep override) → 404
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
    return {"Authorization": (f"Bearer {create_access_token(user.id, user.email)}")}


class _MockLivePriceFetcher:
    """Same in-memory fetcher as test_holdings_api.py — duplicated so this
    file stays standalone (Phase 1 conventions: no test cross-imports)."""

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
    """Reach into the httpx AsyncClient's transport for the FastAPI app
    the `client` fixture wired up (NOT the module-level `app.main.app`)."""
    return client._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def mock_fetcher_factory(client: AsyncClient):
    """Yield a callable that installs `_MockLivePriceFetcher(quotes)` on
    the same FastAPI app instance the `client` fixture uses."""
    app = _client_app(client)

    def _setup(quotes: dict[str, tuple[Decimal, Decimal]]) -> None:
        app.dependency_overrides[get_live_price_fetcher] = lambda: _MockLivePriceFetcher(quotes)

    yield _setup
    app.dependency_overrides.pop(get_live_price_fetcher, None)


async def _create_account(client: AsyncClient, user: User, name: str = "broker") -> int:
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
@pytest.mark.pg_integration
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

    with (
        patch("app.modules.billing.tier_limits.settings") as s_tg,
        patch("app.services.portfolio.rebalancing_service.settings") as s_svc,
    ):
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
            "targets": [{"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"}],
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
# RA05 — aggregate mode w/ unroutable brand-new BUY → 422
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA05_execute_aggregate_unresolvable_trade_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """Defense-in-depth: when aggregate execute receives a plan whose
    suggested trades carry ``account_id=None`` AND the request has no
    top-level scope, we 422 the batch with ``account_unresolved_for_trade``
    rather than silently dropping rows.

    The pure rebalancing module today won't ever emit such a trade
    (brand-new BUYs are skipped with ``missing_price_for_buy`` because
    they have no source position to price against). This test stubs the
    planner to force the case — pinning the guard so a future relaxation
    of the planner can't silently bypass the contract.
    """
    user = await _mk_user(db_session, "rba5@x.tw")
    aid = await _create_account(client, user)
    await _buy(client, user, aid, "2330", qty="100", price="500")
    mock_fetcher_factory({"2330": (Decimal("500"), Decimal("500"))})

    from app.modules.portfolio.rebalancing import RebalanceResult, SuggestedTrade
    from app.services.portfolio.rebalancing_service import RebalancingService

    async def _stubbed_plan(self, **kwargs):
        return RebalanceResult(
            total_portfolio_value=Decimal("50000"),
            suggested_trades=[
                SuggestedTrade(
                    symbol="0050",
                    market="TW_TWSE",
                    action="BUY",
                    qty=Decimal("100"),
                    estimated_price=Decimal("100"),
                    estimated_value=Decimal("10000"),
                    rationale="stubbed unresolvable BUY",
                    account_id=None,  # ← unresolvable
                ),
            ],
            final_allocation_pct={},
            skipped_trades=[],
            cash_residual=Decimal("0"),
        )

    with patch.object(RebalancingService, "preview_rebalance", _stubbed_plan):
        r = await client.post(
            "/api/v1/holdings/rebalance/execute",
            json={
                "targets": [{"symbol": "0050", "market": "TW_TWSE", "target_pct": "100"}],
                # account_id deliberately omitted.
            },
            headers=_auth(user),
        )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "account_unresolved_for_trade"


# ═══════════════════════════════════════════════════════════════════════════
# RA06 — aggregate mode happy path: 2 accounts, distinct trades
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.pg_integration
async def test_RA06_execute_aggregate_two_accounts_dispatches_per_position(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """User has 2 accounts; 2330 in account A, 0050 in account B.
    Aggregate rebalance to 70/30 → SELL 0050 lands in B, BUY 2330 in A.

    Verifies:
      * Top-level account_id omitted is now legal.
      * Each ExecutedTrade.account_id matches the source position's
        account, NOT some shared / default value.
    """
    user = await _mk_user(db_session, "rba6@x.tw")
    aid_a = await _create_account(client, user, name="acct-a")
    aid_b = await _create_account(client, user, name="acct-b")
    await _buy(client, user, aid_a, "2330", qty="100", price="500")  # 50_000 in A
    await _buy(client, user, aid_b, "0050", qty="500", price="100")  # 50_000 in B
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
            # account_id deliberately omitted → aggregate mode.
        },
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["executed"]) == 2
    assert body["failed"] == []
    by_symbol = {row["symbol"]: row for row in body["executed"]}
    assert by_symbol["2330"]["account_id"] == aid_a
    assert by_symbol["2330"]["action"] == "BUY"
    assert by_symbol["0050"]["account_id"] == aid_b
    assert by_symbol["0050"]["action"] == "SELL"

    # Sanity: each account got exactly one new trade row.
    from app.db.models.portfolio.trade import PortfolioTrade

    for aid, expected in ((aid_a, 2), (aid_b, 2)):  # 1 seed + 1 rebalance
        n = await db_session.scalar(
            select(func.count(PortfolioTrade.id)).where(PortfolioTrade.account_id == aid)
        )
        assert int(n or 0) == expected


# ═══════════════════════════════════════════════════════════════════════════
# RA07 — aggregate partial failure: one account succeeds, another fails
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@pytest.mark.pg_integration
async def test_RA07_execute_aggregate_partial_failure_isolated(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """Simulate live drift: account A holds 2330 (100 sh) but the planner
    sees a stale snapshot and asks for SELL 200. The write layer rejects
    with InsufficientShares → `failed`. Account B's BUY still succeeds.

    Verifies per-trade-status isolation across accounts.
    """
    user = await _mk_user(db_session, "rba7@x.tw")
    aid_a = await _create_account(client, user, name="acct-a")
    aid_b = await _create_account(client, user, name="acct-b")
    await _buy(client, user, aid_a, "2330", qty="100", price="500")  # 50_000
    await _buy(client, user, aid_b, "0050", qty="500", price="100")  # 50_000
    mock_fetcher_factory(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )

    # Stub the planner so we control which trades are dispatched, and
    # stub PortfolioTradeService.record_trade so the failure is surgical
    # (no half-INSERT to roll back, no nested awaits crossing the
    # aiosqlite greenlet boundary). What we're pinning is the API
    # contract: a single failure does not poison sibling executions
    # bound to a different account.
    from app.db.models.portfolio.trade import PortfolioTrade
    from app.modules.portfolio.rebalancing import RebalanceResult, SuggestedTrade
    from app.services.portfolio.exceptions import InsufficientShares
    from app.services.portfolio.rebalancing_service import RebalancingService
    from app.services.portfolio.trade_service import PortfolioTradeService

    async def _stub_plan(self, **kwargs):
        return RebalanceResult(
            total_portfolio_value=Decimal("100000"),
            suggested_trades=[
                SuggestedTrade(
                    symbol="2330",
                    market="TW_TWSE",
                    action="SELL",
                    qty=Decimal("60"),
                    estimated_price=Decimal("500"),
                    estimated_value=Decimal("30000"),
                    rationale="stub",
                    account_id=aid_a,
                ),
                SuggestedTrade(
                    symbol="0050",
                    market="TW_TWSE",
                    action="BUY",
                    qty=Decimal("300"),
                    estimated_price=Decimal("100"),
                    estimated_value=Decimal("30000"),
                    rationale="stub",
                    account_id=aid_b,
                ),
            ],
            final_allocation_pct={},
            skipped_trades=[],
            cash_residual=Decimal("0"),
        )

    async def _split_record_trade(self, **kwargs):
        if kwargs["symbol"] == "2330":
            raise InsufficientShares("simulated live drift on 2330")
        # Minimal-but-real persist for the surviving 0050 BUY — we need
        # the session to know about it so the API's commit/refresh
        # cycle works. Skip the FIFO lot/position bookkeeping: this
        # test pins ONLY the per-trade isolation contract.
        trade = PortfolioTrade(
            account_id=kwargs["account_id"],
            symbol=kwargs["symbol"],
            market=kwargs["market"],
            action=kwargs["action"],
            trade_date=kwargs["trade_date"],
            price=kwargs["price"],
            quantity=kwargs["qty"],
        )
        self._db.add(trade)
        await self._db.flush()
        return trade

    with (
        patch.object(RebalancingService, "preview_rebalance", _stub_plan),
        patch.object(PortfolioTradeService, "record_trade", _split_record_trade),
    ):
        r = await client.post(
            "/api/v1/holdings/rebalance/execute",
            json={
                "targets": [
                    {"symbol": "2330", "market": "TW_TWSE", "target_pct": "20"},
                    {"symbol": "0050", "market": "TW_TWSE", "target_pct": "80"},
                ],
            },
            headers=_auth(user),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["executed"]) == 1
    assert body["executed"][0]["symbol"] == "0050"
    assert body["executed"][0]["account_id"] == aid_b
    assert len(body["failed"]) == 1
    assert body["failed"][0]["symbol"] == "2330"
    assert body["failed"][0]["account_id"] == aid_a
    assert body["failed"][0]["error_code"] == "insufficient_shares"


# ═══════════════════════════════════════════════════════════════════════════
# RA08 — per-trade tier-limit halts loop, leaves later trades untouched
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA08_execute_aggregate_tier_limit_halts_remaining(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """When TierLimitExceeded fires mid-batch, the failed row is captured
    and the loop breaks — subsequent trades are NOT attempted (they'd
    hit the same wall). Tests that this still holds in multi-account
    aggregate mode, and the failed row reports the correct account_id.
    """
    user = await _mk_user(db_session, "rba8@x.tw")
    aid_a = await _create_account(client, user, name="acct-a")
    aid_b = await _create_account(client, user, name="acct-b")
    await _buy(client, user, aid_a, "2330", qty="100", price="500")
    await _buy(client, user, aid_b, "0050", qty="500", price="100")
    mock_fetcher_factory(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )

    from app.services.portfolio.exceptions import TierLimitExceeded
    from app.services.portfolio.trade_service import PortfolioTradeService

    call_count = {"n": 0}

    async def _trip_on_first(self, **kwargs):
        call_count["n"] += 1
        raise TierLimitExceeded(
            limit_key="max_trades_per_month",
            current=500,
            limit=500,
        )

    # Stub record_trade to bail with TierLimitExceeded on every call.
    # We rely on the planner naturally emitting 2 trades (one per
    # account); the loop must break after the first failure and the
    # second account's trade must never be attempted.
    with patch.object(PortfolioTradeService, "record_trade", _trip_on_first):
        r = await client.post(
            "/api/v1/holdings/rebalance/execute",
            json={
                "targets": [
                    {"symbol": "2330", "market": "TW_TWSE", "target_pct": "30"},
                    {"symbol": "0050", "market": "TW_TWSE", "target_pct": "70"},
                ],
            },
            headers=_auth(user),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["executed"] == []
    # Only the first trade attempted — loop broke after TierLimitExceeded.
    assert call_count["n"] == 1
    assert len(body["failed"]) == 1
    failed_row = body["failed"][0]
    assert failed_row["error_code"] == "limit_exceeded:max_trades_per_month"
    # account_id is whichever symbol the planner emitted first — both are
    # valid; just confirm it's one of the user's accounts.
    assert failed_row["account_id"] in {aid_a, aid_b}


# ═══════════════════════════════════════════════════════════════════════════
# RA09 — preview echoes per-trade account_id (aggregate mode)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA09_preview_aggregate_emits_per_trade_account_id(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """The preview endpoint must surface per-trade ``account_id`` so the
    UI can render which broker each suggested move will route to BEFORE
    the user confirms. This is the contract the execute endpoint then
    consumes (re-computes the plan server-side; same field, same value).

    Setup: 2 accounts, each holds one stock. Aggregate preview must
    echo each suggested trade's account_id to the corresponding source.
    """
    user = await _mk_user(db_session, "rba9@x.tw")
    aid_a = await _create_account(client, user, name="acct-a")
    aid_b = await _create_account(client, user, name="acct-b")
    await _buy(client, user, aid_a, "2330", qty="100", price="500")  # 50_000
    await _buy(client, user, aid_b, "0050", qty="500", price="100")  # 50_000
    mock_fetcher_factory(
        {
            "2330": (Decimal("500"), Decimal("500")),
            "0050": (Decimal("100"), Decimal("100")),
        }
    )

    r = await client.post(
        "/api/v1/holdings/rebalance/preview",
        json={
            "targets": [
                {"symbol": "2330", "market": "TW_TWSE", "target_pct": "70"},
                {"symbol": "0050", "market": "TW_TWSE", "target_pct": "30"},
            ],
        },
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    trades = body["suggested_trades"]
    assert len(trades) == 2
    by_symbol = {row["symbol"]: row for row in trades}
    assert by_symbol["2330"]["account_id"] == aid_a
    assert by_symbol["0050"]["account_id"] == aid_b


# ═══════════════════════════════════════════════════════════════════════════
# RA10 — defense-in-depth: foreign per-trade account_id → 404
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_RA10_execute_foreign_per_trade_account_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_fetcher_factory,
) -> None:
    """If a planner-emitted SuggestedTrade somehow carries an account_id
    the requesting user doesn't own (future refactor regression), the
    execute endpoint must surface 404 portfolio_account_not_found via
    its defense-in-depth ownership re-check.

    Per Phase 2 design (spec §9.5), 404 collapses with 403 to avoid
    leaking "account exists but not yours". The check is re-asserted
    here even though the planner sources from list_by_user, because
    Stanley's portfolio domain pattern is to never trust the upstream
    layer for ownership.
    """
    # User A owns account A; user B owns nothing. We make B request an
    # execute, but stub the rebalancing service so its planner returns a
    # trade with account_id pointing at A's account.
    a = await _mk_user(db_session, "rba10a@x.tw")
    b = await _mk_user(db_session, "rba10b@x.tw")
    aid_a = await _create_account(client, a)
    mock_fetcher_factory({"2330": (Decimal("500"), Decimal("500"))})

    from app.modules.portfolio.rebalancing import RebalanceResult, SuggestedTrade
    from app.services.portfolio.rebalancing_service import RebalancingService

    async def _stubbed_plan(self, **kwargs):
        return RebalanceResult(
            total_portfolio_value=Decimal("50000"),
            suggested_trades=[
                SuggestedTrade(
                    symbol="2330",
                    market="TW_TWSE",
                    action="BUY",
                    qty=Decimal("10"),
                    estimated_price=Decimal("500"),
                    estimated_value=Decimal("5000"),
                    rationale="stubbed for RA10",
                    account_id=aid_a,  # ← foreign to requester `b`
                )
            ],
            final_allocation_pct={"2330|TW_TWSE": Decimal("100")},
            skipped_trades=[],
            cash_residual=Decimal("0"),
        )

    with patch.object(RebalancingService, "preview_rebalance", _stubbed_plan):
        r = await client.post(
            "/api/v1/holdings/rebalance/execute",
            json={
                "targets": [{"symbol": "2330", "market": "TW_TWSE", "target_pct": "100"}],
            },
            headers=_auth(b),
        )
    assert r.status_code == 404, r.text
    assert r.json()["message"] == "portfolio_account_not_found"
