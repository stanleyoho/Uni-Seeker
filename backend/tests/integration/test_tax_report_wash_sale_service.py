"""Integration tests for TaxReportService wash-sale flow — Phase 5 (Round 11).

Coverage:
    IW01 generate_form_8949_with_wash_sales — PRO user happy path
    IW02 apply_wash_sales=false default keeps Round-10 CSV shape
    IW03 apply_wash_sales=true CSV includes Code='W' + Adjustment
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User


async def _mk_user(
    db: AsyncSession,
    email: str,
    tier: UserTier = UserTier.PRO,
    username: str | None = None,
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


async def _create_account(client: AsyncClient, user: User, name: str = "IB") -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": name, "market": "US_NASDAQ", "broker": "IBKR"},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _post_trade(
    client: AsyncClient,
    user: User,
    aid: int,
    action: str,
    symbol: str,
    qty: str,
    price: str,
    trade_date: str,
    fee: str = "0",
    tax: str = "0",
) -> int:
    r = await client.post(
        "/api/v1/holdings/trades",
        json={
            "account_id": aid,
            "action": action,
            "symbol": symbol,
            "market": "US_NASDAQ",
            "qty": qty,
            "price": price,
            "trade_date": trade_date,
            "fee": fee,
            "tax": tax,
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _parse_csv(body: bytes) -> tuple[list[str], list[list[str]]]:
    import csv as csv_mod
    import io

    text = body.decode("utf-8")
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv_mod.reader(io.StringIO(text))
    rows = list(reader)
    return rows[0], rows[1:]


# ── service layer ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_IW01_generate_with_wash_sales_pro_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PRO user: a loss SELL + nearby replacement BUY → detector flags it."""
    from app.services.portfolio import TaxReportService

    user = await _mk_user(db_session, "wash1@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    # Loss leg: buy 100 @ 150, sell 100 @ 100 → -5000 loss.
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "150", "2024-01-05")
    await _post_trade(client, user, aid, "SELL", "AAPL", "100", "100", "2024-06-01")
    # Replacement BUY 20 days after the sale → wash sale.
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "120", "2024-06-21")

    service = TaxReportService(db_session, user)
    matches, adjustments, summary = await service.generate_form_8949_with_wash_sales()
    assert len(matches) == 1
    assert matches[0].is_wash_sale is True
    assert matches[0].gain_loss == Decimal("0")
    assert matches[0].wash_sale_disallowed_loss == Decimal("5000")
    assert len(adjustments) == 1
    assert adjustments[0].disallowed_loss == Decimal("5000")
    # Year rollup: loss fully disallowed → net 0.
    assert summary[2024].total_net == Decimal("0")


@pytest.mark.asyncio
async def test_IW02_apply_wash_sales_flag_default_false(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Without apply_wash_sales=true the CSV stays Round-10 compatible."""
    user = await _mk_user(db_session, "wash2@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "150", "2024-01-05")
    await _post_trade(client, user, aid, "SELL", "AAPL", "100", "100", "2024-06-01")
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "120", "2024-06-21")

    r = await client.get(
        "/api/v1/holdings/exports/form8949.csv",
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert len(rows) == 1
    # Code column blank, Adjustment blank, Wash Sale=false (legacy shape).
    assert rows[0][5] == ""
    assert rows[0][6] == ""
    assert rows[0][10] == "false"
    # Loss preserved (not disallowed) — backward-compat behaviour.
    assert Decimal(rows[0][7]) == Decimal("-5000")


@pytest.mark.asyncio
async def test_IW03_apply_wash_sales_csv_includes_W_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """apply_wash_sales=true → Code='W', Adjustment positive, Gain/Loss=0."""
    user = await _mk_user(db_session, "wash3@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "150", "2024-01-05")
    await _post_trade(client, user, aid, "SELL", "AAPL", "100", "100", "2024-06-01")
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "120", "2024-06-21")

    r = await client.get(
        "/api/v1/holdings/exports/form8949.csv?apply_wash_sales=true",
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert len(rows) == 1
    assert rows[0][5] == "W"  # Code
    assert Decimal(rows[0][6]) == Decimal("5000")  # Adjustment
    assert Decimal(rows[0][7]) == Decimal("0")  # Gain/Loss zeroed
    assert rows[0][10] == "true"  # Wash Sale flag
