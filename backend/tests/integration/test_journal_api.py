"""Integration tests for Trade Journal API — T15–T20.

Tests cover position consistency across BUY/SELL operations and cross-market
account isolation.

SQLite compatibility note: The Trade model uses PostgreSQL JSONB for the ``tags``
column. We patch ``SQLiteTypeCompiler`` to render JSONB as JSON so that
in-memory SQLite works for testing without changing the production model.
"""
from __future__ import annotations

from datetime import date

# ── Patch SQLite compiler to handle PostgreSQL JSONB ─────────────────────────
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler as _SQLiteTypeCompiler


def _visit_JSONB(self: _SQLiteTypeCompiler, type_: object, **kwargs: object) -> str:  # type: ignore[override]
    return self.visit_JSON(type_, **kwargs)  # type: ignore[arg-type]


_SQLiteTypeCompiler.visit_JSONB = _visit_JSONB  # type: ignore[attr-defined]
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.main import create_app
from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

TRADE_DATE = date(2026, 1, 15).isoformat()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def app_with_journal_db():
    """Shared app fixture with in-memory SQLite and dependency override."""
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ── Helper ─────────────────────────────────────────────────────────────────────

async def _create_account(client: AsyncClient, name: str, market: str, currency: str) -> int:
    resp = await client.post("/api/v1/journal/accounts", json={
        "name": name,
        "market": market,
        "currency": currency,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _add_trade(
    client: AsyncClient,
    account_id: int,
    action: str,
    symbol: str,
    market: str,
    price: float,
    quantity: float,
) -> dict:
    resp = await client.post(f"/api/v1/journal/accounts/{account_id}/trades", json={
        "symbol": symbol,
        "market": market,
        "action": action,
        "date": TRADE_DATE,
        "price": str(price),
        "quantity": str(quantity),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _get_position(client: AsyncClient, account_id: int) -> list[dict]:
    resp = await client.get(f"/api/v1/journal/accounts/{account_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()["positions"]


# ── T15: BUY creates position ──────────────────────────────────────────────────

async def test_t15_buy_creates_position(app_with_journal_db) -> None:
    """T15: BUY 100 shares @100 → position qty=100, total_cost=10000."""
    transport = ASGITransport(app=app_with_journal_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account_id = await _create_account(client, "TW Account", "TW", "TWD")
        await _add_trade(client, account_id, "BUY", "2330", "TW", 100.0, 100.0)

        positions = await _get_position(client, account_id)
        assert len(positions) == 1
        pos = positions[0]
        assert pos["symbol"] == "2330"
        assert float(pos["quantity"]) == 100.0
        assert float(pos["total_cost"]) == pytest.approx(10000.0)
        assert pos["is_closed"] is False


# ── T16: SELL updates position ─────────────────────────────────────────────────

async def test_t16_sell_updates_position(app_with_journal_db) -> None:
    """T16: BUY 100@100 → SELL 40@150 → qty=60, realized_pnl=+2000."""
    transport = ASGITransport(app=app_with_journal_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account_id = await _create_account(client, "T16 Account", "TW", "TWD")
        await _add_trade(client, account_id, "BUY", "2330", "TW", 100.0, 100.0)
        await _add_trade(client, account_id, "SELL", "2330", "TW", 150.0, 40.0)

        positions = await _get_position(client, account_id)
        assert len(positions) == 1
        pos = positions[0]
        assert float(pos["quantity"]) == pytest.approx(60.0)
        # Realized PnL = (150 - 100) * 40 = 2000
        assert float(pos["realized_pnl"]) == pytest.approx(2000.0)
        assert pos["is_closed"] is False


# ── T17: Full sell closes position ─────────────────────────────────────────────

async def test_t17_full_sell_closes_position(app_with_journal_db) -> None:
    """T17: BUY 100@100 → SELL 100@150 → position is_closed=True, not in open positions."""
    transport = ASGITransport(app=app_with_journal_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account_id = await _create_account(client, "T17 Account", "TW", "TWD")
        await _add_trade(client, account_id, "BUY", "2330", "TW", 100.0, 100.0)
        await _add_trade(client, account_id, "SELL", "2330", "TW", 150.0, 100.0)

        # Account detail should return no open positions (is_closed=True filtered out)
        positions = await _get_position(client, account_id)
        open_symbols = [p["symbol"] for p in positions]
        assert "2330" not in open_symbols


# ── T19: Multiple trades consistent ────────────────────────────────────────────

async def test_t19_multiple_trades_consistent(app_with_journal_db) -> None:
    """T19: BUY 100@100, BUY 80@110, BUY 60@120 → SELL 110 → qty=130 remaining."""
    transport = ASGITransport(app=app_with_journal_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        account_id = await _create_account(client, "T19 Account", "US", "USD")
        await _add_trade(client, account_id, "BUY", "AAPL", "US", 100.0, 100.0)
        await _add_trade(client, account_id, "BUY", "AAPL", "US", 110.0, 80.0)
        await _add_trade(client, account_id, "BUY", "AAPL", "US", 120.0, 60.0)
        # Total bought = 240, sell 110 → remaining = 130
        await _add_trade(client, account_id, "SELL", "AAPL", "US", 130.0, 110.0)

        positions = await _get_position(client, account_id)
        assert len(positions) == 1
        pos = positions[0]
        assert pos["symbol"] == "AAPL"
        assert float(pos["quantity"]) == pytest.approx(130.0)


# ── T20: Cross-market no collision ─────────────────────────────────────────────

async def test_t20_cross_market_no_collision(app_with_journal_db) -> None:
    """T20: TW account with 2330 TW and US account with 2330 US → separate positions, no interference."""
    transport = ASGITransport(app=app_with_journal_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tw_account_id = await _create_account(client, "TW Account", "TW", "TWD")
        us_account_id = await _create_account(client, "US Account", "US", "USD")

        # BUY 2330 in TW account
        await _add_trade(client, tw_account_id, "BUY", "2330", "TW", 100.0, 100.0)
        # BUY 2330 in US account (different market)
        await _add_trade(client, us_account_id, "BUY", "2330", "US", 200.0, 50.0)

        tw_positions = await _get_position(client, tw_account_id)
        us_positions = await _get_position(client, us_account_id)

        assert len(tw_positions) == 1
        assert len(us_positions) == 1

        tw_pos = tw_positions[0]
        us_pos = us_positions[0]

        # Positions are separate and contain correct data
        assert tw_pos["symbol"] == "2330"
        assert tw_pos["market"] == "TW"
        assert float(tw_pos["quantity"]) == pytest.approx(100.0)
        assert float(tw_pos["total_cost"]) == pytest.approx(10000.0)

        assert us_pos["symbol"] == "2330"
        assert us_pos["market"] == "US"
        assert float(us_pos["quantity"]) == pytest.approx(50.0)
        assert float(us_pos["total_cost"]) == pytest.approx(10000.0)
