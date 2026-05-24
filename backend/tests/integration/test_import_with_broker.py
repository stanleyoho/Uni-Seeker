"""Integration tests — broker-aware CSV import (Round 10).

Exercises the end-to-end flow:

* `GET /imports/brokers` lists adapters.
* `POST /imports/csv?broker_key=X` dispatches to the named adapter.
* `POST /imports/csv` without `broker_key` auto-detects.
* Override semantics: explicit broker_key wins even when content
  matches another adapter's heuristic.

Reuses helpers / fixtures from `test_holdings_csv_import` style.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.db.models.portfolio.account import PortfolioAccount
from app.db.models.portfolio.trade import PortfolioTrade
from app.models.enums import UserTier
from app.models.user import User


# ── helpers ─────────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    email: str,
    tier: UserTier = UserTier.PRO,
) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=email.split("@")[0],
    )
    u.tier = tier
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.email)}"}


def _csv_headers(user: User) -> dict[str, str]:
    return {**_auth(user), "Content-Type": "text/csv"}


async def _create_account_via_api(
    client: AsyncClient, user: User, market: str = "TW_TWSE"
) -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": "Broker", "market": market},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _trade_count(db: AsyncSession, user_id: int) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(PortfolioTrade)
        .join(
            PortfolioAccount,
            PortfolioAccount.id == PortfolioTrade.account_id,
        )
        .where(PortfolioAccount.user_id == user_id)
    ) or 0


# ── sample CSV bodies ───────────────────────────────────────────────────────


_IB = (
    "Statement,Header,Field Name,Field Value\n"
    "Trades,Header,DataDiscriminator,Asset Category,Symbol,Date/Time,Quantity,T. Price,Comm/Fee,Currency,OrderID\n"
    "Trades,Data,Order,Stocks,NVDA,2026-04-15;09:35:11,100,500.00,-1.00,USD,O111\n"
    "Trades,Data,Order,Stocks,NVDA,2026-04-16;10:00:00,-50,510.00,-1.00,USD,O112\n"
).encode("utf-8")


_YUANTA = (
    "交易日期,股票代號,股票名稱,交易類別,股數,價格,手續費,交易稅\n"
    "2026/04/15,2330,台積電,買進,1000,580,150,0\n"
    "2026/04/20,2330,台積電,賣出,500,600,90,180\n"
).encode("utf-8")


_FUBON = (
    "日期,代號,名稱,委託類別,股數,單價,手續費,證交稅\n"
    "2026/04/15,2330,台積電,B,1000,580,150,0\n"
    "2026/04/16,2454,聯發科,S,200,1000,90,300\n"
).encode("utf-8")


_SCHWAB = (
    "Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount\n"
    "04/15/2026,Buy,NVDA,NVIDIA CORP,100,500.00,$0.00,$50000.00\n"
    "04/16/2026,Sell,NVDA,NVIDIA CORP,50,510.00,$0.00,$25500.00\n"
).encode("utf-8")


_FIDELITY = (
    "Run Date,Action,Symbol,Description,Type,Quantity,Price ($),Commission ($),Fees ($),Amount ($)\n"
    "04/15/2026,YOU BOUGHT,NVDA,NVIDIA CORP,Cash,100,500.00,0.00,0.00,-50000.00\n"
    "04/16/2026,YOU SOLD,NVDA,NVIDIA CORP,Cash,50,510.00,0.00,0.00,25500.00\n"
).encode("utf-8")


# ── tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_brokers_returns_default_registry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers1@x.tw")
    r = await client.get("/api/v1/holdings/imports/brokers", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    keys = {b["broker_key"] for b in body["brokers"]}
    assert {
        "interactive_brokers",
        "yuanta",
        "fubon",
        "schwab",
        "fidelity",
        "generic",
    }.issubset(keys)
    # Generic should be last (auto-detect fallback).
    assert body["brokers"][-1]["broker_key"] == "generic"


@pytest.mark.asyncio
async def test_explicit_broker_key_ib(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers2@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user, market="US_NASDAQ")
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&broker_key=interactive_brokers&dry_run=false",
        content=_IB,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 2
    assert body["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 2


@pytest.mark.asyncio
async def test_explicit_broker_key_yuanta(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers3@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&broker_key=yuanta&dry_run=false",
        content=_YUANTA,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 2
    assert body["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 2


@pytest.mark.asyncio
async def test_auto_detect_fubon(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers4@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    # No broker_key — should auto-detect Fubon.
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=true",
        content=_FUBON,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 2
    assert body["failed_rows"] == 0
    # Dry-run — no writes.
    assert await _trade_count(db_session, uid) == 0


@pytest.mark.asyncio
async def test_auto_detect_schwab_commits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers5@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user, market="US_NYSE")
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=_SCHWAB,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parsed_rows"] == 2
    assert body["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 2


@pytest.mark.asyncio
async def test_auto_detect_fidelity_with_dividend_rejection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Fidelity CSV with a YOU BOUGHT + YOU SOLD + DIVIDEND row.

    Commit mode: the dividend row triggers atomic rollback, so zero
    trades land. Dry-run would report 2 OK + 1 failed.
    """
    user = await _mk_user(db_session, "brokers6@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user, market="US_NYSE")
    body_with_div = (
        _FIDELITY
        + b"04/20/2026,DIVIDEND RECEIVED,NVDA,NVIDIA CORP,Cash,0,0.00,0.00,0.00,45.00\n"
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=body_with_div,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failed_rows"] == 1
    assert body["successful_rows"] == 0
    assert body["errors"][0]["error"] == "dividend_actions_not_supported"
    assert await _trade_count(db_session, uid) == 0


@pytest.mark.asyncio
async def test_unknown_broker_key_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "brokers7@x.tw")
    aid = await _create_account_via_api(client, user)
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&broker_key=does_not_exist",
        content=_YUANTA,
        headers=_csv_headers(user),
    )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "invalid_csv_format"


@pytest.mark.asyncio
async def test_explicit_broker_key_overrides_autodetect(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Forcing broker_key=generic on a Yuanta-shaped file should 422.

    The user asked for the generic adapter; generic doesn't understand
    Chinese headers; it raises ValueError → endpoint 422s. This proves
    we honour the explicit key and don't silently fall through to
    auto-detect.
    """
    user = await _mk_user(db_session, "brokers8@x.tw")
    aid = await _create_account_via_api(client, user)
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&broker_key=generic",
        content=_YUANTA,
        headers=_csv_headers(user),
    )
    assert r.status_code == 422, r.text
