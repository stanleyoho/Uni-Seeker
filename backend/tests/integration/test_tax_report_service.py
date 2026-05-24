"""Integration tests for TaxReportService — Phase 4+ Tax Export (Round 10).

Coverage:
    I01 happy-path matched pairs via service.generate_form_8949
    I02 FREE tier → 403 feature_unavailable:tax_export
    I03 BASIC tier → 403 feature_unavailable:tax_export
    I04 PRO tier passes
    I05 tax_year filter narrows matches
    I06 account_id filter scopes to one account
    I07 form_8949 CSV column layout + BOM
    I08 schedule_d CSV layout
    I09 empty trades returns header-only CSV
    I10 cross-user isolation (other user's trades invisible)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User

# ── Helpers ────────────────────────────────────────────────────────────


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


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_I01_happy_path_matched_pairs(client: AsyncClient, db_session: AsyncSession) -> None:
    """One BUY + one SELL → one Form 8949 row with correct numbers."""
    from app.services.portfolio import TaxReportService

    user = await _mk_user(db_session, "tax1@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "100", "150", "2024-01-05")
    await _post_trade(client, user, aid, "SELL", "AAPL", "100", "200", "2024-07-01")

    service = TaxReportService(db_session, user)
    matches, summary = await service.generate_form_8949()
    assert len(matches) == 1
    m = matches[0]
    assert m.symbol == "AAPL"
    assert m.quantity == Decimal("100")
    assert m.cost_basis == Decimal("15000")
    assert m.proceeds == Decimal("20000")
    assert m.gain_loss == Decimal("5000")
    assert m.term == "SHORT"
    assert 2024 in summary
    assert summary[2024].short_term_net == Decimal("5000")
    assert summary[2024].total_matches == 1


@pytest.mark.asyncio
async def test_I02_free_tier_403_feature_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier hits the service-level tax_export gate."""
    user = await _mk_user(db_session, "tax2@x.tw", UserTier.FREE)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "10", "100", "2024-01-05")

    with patch("app.services.portfolio.tax_report_service.settings") as s:
        s.enable_monetization = True
        r = await client.get("/api/v1/holdings/exports/form8949.csv", headers=_auth(user))
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:tax_export"


@pytest.mark.asyncio
async def test_I03_basic_tier_403_feature_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """BASIC tier also lacks tax_export; only PRO has the flag."""
    user = await _mk_user(db_session, "tax3@x.tw", UserTier.BASIC)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "10", "100", "2024-01-05")

    with patch("app.services.portfolio.tax_report_service.settings") as s:
        s.enable_monetization = True
        r = await client.get("/api/v1/holdings/exports/schedule_d.csv", headers=_auth(user))
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:tax_export"


@pytest.mark.asyncio
async def test_I04_pro_tier_passes(client: AsyncClient, db_session: AsyncSession) -> None:
    """PRO tier passes the gate even with monetization on."""
    user = await _mk_user(db_session, "tax4@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "10", "100", "2024-01-05")

    with patch("app.services.portfolio.tax_report_service.settings") as s:
        s.enable_monetization = True
        r = await client.get("/api/v1/holdings/exports/form8949.csv", headers=_auth(user))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_I05_tax_year_filter(client: AsyncClient, db_session: AsyncSession) -> None:
    """Two SELLs in different years; ?tax_year=2024 keeps only one."""
    from app.services.portfolio import TaxReportService

    user = await _mk_user(db_session, "tax5@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "50", "100", "2023-01-01")
    await _post_trade(client, user, aid, "SELL", "AAPL", "20", "120", "2024-06-01")
    await _post_trade(client, user, aid, "SELL", "AAPL", "20", "130", "2025-06-01")

    service = TaxReportService(db_session, user)
    matches_all, _ = await service.generate_form_8949()
    assert len(matches_all) == 2

    matches_2024, summary_2024 = await service.generate_form_8949(tax_year=2024)
    assert len(matches_2024) == 1
    assert matches_2024[0].sale_date.year == 2024
    assert set(summary_2024) == {2024}


@pytest.mark.asyncio
async def test_I06_account_id_filter(client: AsyncClient, db_session: AsyncSession) -> None:
    """Two accounts; account_id filter narrows to one."""
    from app.services.portfolio import TaxReportService

    user = await _mk_user(db_session, "tax6@x.tw", UserTier.PRO)
    a1 = await _create_account(client, user, name="acct1")
    a2 = await _create_account(client, user, name="acct2")
    await _post_trade(client, user, a1, "BUY", "AAPL", "10", "100", "2024-01-01")
    await _post_trade(client, user, a1, "SELL", "AAPL", "10", "150", "2024-06-01")
    await _post_trade(client, user, a2, "BUY", "MSFT", "5", "200", "2024-02-01")
    await _post_trade(client, user, a2, "SELL", "MSFT", "5", "250", "2024-07-01")

    service = TaxReportService(db_session, user)
    matches, _ = await service.generate_form_8949(account_id=a1)
    assert len(matches) == 1
    assert matches[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_I07_form_8949_csv_layout_and_bom(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CSV column order + BOM prefix + content sanity."""
    user = await _mk_user(db_session, "tax7@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "10", "100", "2024-01-01")
    await _post_trade(client, user, aid, "SELL", "AAPL", "10", "150", "2024-06-01")

    r = await client.get("/api/v1/holdings/exports/form8949.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    header, rows = _parse_csv(r.content)
    assert header == [
        "Description",
        "Date Acquired",
        "Date Sold",
        "Proceeds",
        "Cost Basis",
        "Code",
        "Adjustment",
        "Gain/Loss",
        "Term",
        "Holding Period Days",
        "Wash Sale",
    ]
    assert len(rows) == 1
    assert "AAPL" in rows[0][0]
    assert rows[0][1] == "2024-01-01"
    assert rows[0][2] == "2024-06-01"
    assert Decimal(rows[0][3]) == Decimal("1500")
    assert Decimal(rows[0][4]) == Decimal("1000")
    assert Decimal(rows[0][7]) == Decimal("500")
    assert rows[0][8] == "SHORT"
    assert rows[0][10] == "false"


@pytest.mark.asyncio
async def test_I08_schedule_d_csv_layout(client: AsyncClient, db_session: AsyncSession) -> None:
    """Schedule D rollup CSV — header + per-year row."""
    user = await _mk_user(db_session, "tax8@x.tw", UserTier.PRO)
    aid = await _create_account(client, user)
    await _post_trade(client, user, aid, "BUY", "AAPL", "10", "100", "2024-01-01")
    await _post_trade(client, user, aid, "SELL", "AAPL", "10", "150", "2024-06-01")

    r = await client.get("/api/v1/holdings/exports/schedule_d.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert header == [
        "tax_year",
        "short_term_gain",
        "short_term_loss",
        "short_term_net",
        "long_term_gain",
        "long_term_loss",
        "long_term_net",
        "total_net",
        "total_matches",
    ]
    assert len(rows) == 1
    assert rows[0][0] == "2024"
    assert Decimal(rows[0][1]) == Decimal("500")  # short-term gain
    assert Decimal(rows[0][3]) == Decimal("500")  # short-term net
    assert Decimal(rows[0][7]) == Decimal("500")  # total net
    assert rows[0][8] == "1"


@pytest.mark.asyncio
async def test_I09_empty_trades_returns_header_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """No trades → CSV with header only (file is never zero-bytes)."""
    user = await _mk_user(db_session, "tax9@x.tw", UserTier.PRO)

    r1 = await client.get("/api/v1/holdings/exports/form8949.csv", headers=_auth(user))
    assert r1.status_code == 200
    header, rows = _parse_csv(r1.content)
    assert header[0] == "Description"
    assert rows == []

    r2 = await client.get("/api/v1/holdings/exports/schedule_d.csv", headers=_auth(user))
    assert r2.status_code == 200
    header2, rows2 = _parse_csv(r2.content)
    assert header2[0] == "tax_year"
    assert rows2 == []


@pytest.mark.asyncio
async def test_I10_cross_user_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    """User B cannot see user A's trades via tax export."""
    from app.services.portfolio import TaxReportService

    user_a = await _mk_user(db_session, "tax10a@x.tw", UserTier.PRO, username="userA")
    user_b = await _mk_user(db_session, "tax10b@x.tw", UserTier.PRO, username="userB")
    aid_a = await _create_account(client, user_a, name="A-account")
    await _post_trade(client, user_a, aid_a, "BUY", "AAPL", "10", "100", "2024-01-01")
    await _post_trade(client, user_a, aid_a, "SELL", "AAPL", "10", "150", "2024-06-01")

    # User B has no accounts of their own → empty.
    service_b = TaxReportService(db_session, user_b)
    matches_b, summary_b = await service_b.generate_form_8949()
    assert matches_b == []
    assert summary_b == {}

    # B cannot peek at A's account_id.
    matches_peek, _ = await service_b.generate_form_8949(account_id=aid_a)
    assert matches_peek == []
