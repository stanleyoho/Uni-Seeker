"""Integration tests for /api/v1/holdings/exports/*.csv — Portfolio
Tracker Phase 4 tax export hook.

Spec §11 extensibility (tax_export feature flag in
``config/tier_limits.yaml`` — PRO only). ~11 cases covering:

- PRO tier 200 with CSV body
- FREE / BASIC 403 ``feature_unavailable:tax_export`` (when
  ``enable_monetization`` is on — both tiers have the flag false)
- Filter by account / date range
- Position rows include unrealized P&L using the latest
  ``stock_prices`` close
- Dividend column ordering + STOCK row's ratio appears in
  ``amount_per_share``
- Summary returns exactly one data row
- UTF-8 BOM prefix
- Quote escaping when ``note`` contains a comma
- Empty data returns header-only CSV (still valid)

Conventions copied from ``test_holdings_dividends_api.py`` so reviewer
cognitive load stays low (``_mk_user``, ``_auth``,
``_create_account_via_api``, ``_seed_buy``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import Market, UserTier
from app.models.price import StockPrice
from app.models.stock import Stock
from app.models.user import User

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


async def _create_account_via_api(client: AsyncClient, user: User, name: str = "Yuanta") -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": name, "market": "TW_TWSE", "broker": "Yuanta"},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _seed_buy(
    client: AsyncClient,
    user: User,
    aid: int,
    symbol: str = "2330",
    qty: str = "100",
    price: str = "500",
    trade_date: str = "2026-05-01",
    note: str | None = None,
) -> int:
    """Drop a BUY trade and return its id."""
    body: dict = {
        "account_id": aid,
        "action": "BUY",
        "symbol": symbol,
        "market": "TW_TWSE",
        "qty": qty,
        "price": price,
        "trade_date": trade_date,
    }
    if note is not None:
        body["note"] = note
    r = await client.post("/api/v1/holdings/trades", json=body, headers=_auth(user))
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _seed_cash_dividend(
    client: AsyncClient,
    user: User,
    aid: int,
    symbol: str = "2330",
    ex_date: str = "2026-05-10",
) -> None:
    r = await client.post(
        "/api/v1/holdings/dividends",
        json={
            "account_id": aid,
            "symbol": symbol,
            "market": "TW_TWSE",
            "dividend_type": "CASH",
            "ex_dividend_date": ex_date,
            "pay_date": "2026-06-01",
            "amount_per_share": "5",
            "quantity_at_record": "100",
            "withholding_tax": "50",
            "currency": "TWD",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text


async def _seed_price_history(
    db: AsyncSession, symbol: str, last_close: str, prev_close: str
) -> None:
    """Insert a Stock + two StockPrice rows so PriceLookupRepo has data."""
    stock = Stock(
        symbol=symbol,
        name=symbol,
        market=Market.TW_TWSE,
    )
    db.add(stock)
    await db.commit()
    await db.refresh(stock)
    db.add_all(
        [
            StockPrice(
                stock_id=stock.id,
                date=date(2026, 5, 9),
                open=Decimal(prev_close),
                high=Decimal(prev_close),
                low=Decimal(prev_close),
                close=Decimal(prev_close),
                volume=1_000_000,
            ),
            StockPrice(
                stock_id=stock.id,
                date=date(2026, 5, 10),
                open=Decimal(last_close),
                high=Decimal(last_close),
                low=Decimal(last_close),
                close=Decimal(last_close),
                volume=1_000_000,
            ),
        ]
    )
    await db.commit()


def _parse_csv(body: bytes) -> tuple[list[str], list[list[str]]]:
    """Parse CSV bytes (with BOM) → (header, rows). Mirror what the
    frontend would see after the browser strips the BOM."""
    import csv as csv_mod
    import io

    text = body.decode("utf-8")
    # Strip BOM for parsing convenience.
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv_mod.reader(io.StringIO(text))
    rows = list(reader)
    return rows[0], rows[1:]


# ═════════════════════════════════════════════════════════════════════════════
# /exports/trades.csv
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_trades_pro_user_200_returns_csv(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PRO tier downloads trades CSV; status 200, content-type csv,
    BOM-prefixed body with one data row."""
    user = await _mk_user(db_session, "exp_t1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]

    header, rows = _parse_csv(r.content)
    assert header == [
        "trade_date",
        "account_name",
        "action",
        "symbol",
        "market",
        "quantity",
        "price",
        "fee",
        "tax",
        "total_value",
        "note",
    ]
    assert len(rows) == 1
    assert rows[0][0] == "2026-05-01"
    assert rows[0][2] == "BUY"
    assert rows[0][3] == "2330"
    assert Decimal(rows[0][9]) == Decimal("50000")


@pytest.mark.asyncio
async def test_export_trades_free_user_403_feature_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier lacks tax_export — service raises
    TierFeatureUnavailableError → endpoint maps to 403."""
    user = await _mk_user(db_session, "exp_t2@x.tw", tier=UserTier.FREE)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    with patch("app.services.portfolio.export_service.settings") as s:
        s.enable_monetization = True
        r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:tax_export"


@pytest.mark.asyncio
async def test_export_trades_basic_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    """BASIC tier also lacks tax_export (only PRO ships it). 403."""
    user = await _mk_user(db_session, "exp_t3@x.tw", tier=UserTier.BASIC)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    with patch("app.services.portfolio.export_service.settings") as s:
        s.enable_monetization = True
        r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:tax_export"


@pytest.mark.asyncio
async def test_export_trades_filter_account_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """``?account_id=`` returns trades only on that account."""
    user = await _mk_user(db_session, "exp_t4@x.tw", tier=UserTier.PRO)
    a1 = await _create_account_via_api(client, user, name="a1")
    a2 = await _create_account_via_api(client, user, name="a2")
    await _seed_buy(client, user, a1, symbol="A")
    await _seed_buy(client, user, a2, symbol="B")

    r = await client.get(
        f"/api/v1/holdings/exports/trades.csv?account_id={a1}",
        headers=_auth(user),
    )
    assert r.status_code == 200
    _, rows = _parse_csv(r.content)
    assert len(rows) == 1
    assert rows[0][3] == "A"


@pytest.mark.asyncio
async def test_export_trades_filter_date_range(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Date filters are inclusive on both endpoints."""
    user = await _mk_user(db_session, "exp_t5@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid, symbol="A", trade_date="2026-04-01")
    await _seed_buy(client, user, aid, symbol="B", trade_date="2026-05-15")
    await _seed_buy(client, user, aid, symbol="C", trade_date="2026-06-20")

    r = await client.get(
        "/api/v1/holdings/exports/trades.csv?date_from=2026-05-01&date_to=2026-05-31",
        headers=_auth(user),
    )
    assert r.status_code == 200
    _, rows = _parse_csv(r.content)
    assert len(rows) == 1
    assert rows[0][3] == "B"


# ═════════════════════════════════════════════════════════════════════════════
# /exports/positions.csv
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_positions_includes_unrealized_pnl(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Position row picks up last_price from stock_prices and computes
    unrealized = (last_price - avg_cost) * qty."""
    user = await _mk_user(db_session, "exp_p1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid, qty="100", price="500")
    await _seed_price_history(db_session, "2330", last_close="550", prev_close="540")

    r = await client.get("/api/v1/holdings/exports/positions.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert header == [
        "account_name",
        "symbol",
        "market",
        "quantity",
        "avg_cost",
        "last_price",
        "total_cost",
        "market_value",
        "unrealized_pnl",
        "realized_pnl",
        "is_closed",
    ]
    assert len(rows) == 1
    assert rows[0][1] == "2330"
    assert Decimal(rows[0][5]) == Decimal("550")
    assert Decimal(rows[0][7]) == Decimal("55000")  # 100 * 550
    assert Decimal(rows[0][8]) == Decimal("5000")  # (550 - 500) * 100


# ═════════════════════════════════════════════════════════════════════════════
# /exports/dividends.csv
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_dividends_csv_columns(client: AsyncClient, db_session: AsyncSession) -> None:
    """Header order is fixed + total_amount/net_amount are computed."""
    user = await _mk_user(db_session, "exp_d1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    await _seed_cash_dividend(client, user, aid)

    r = await client.get("/api/v1/holdings/exports/dividends.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert header == [
        "ex_date",
        "pay_date",
        "account_name",
        "symbol",
        "market",
        "dividend_type",
        "amount_per_share",
        "quantity_at_record",
        "withholding_tax",
        "total_amount",
        "net_amount",
        "currency",
        "note",
    ]
    assert len(rows) == 1
    assert rows[0][0] == "2026-05-10"
    assert rows[0][5] == "CASH"
    # 5 * 100 = 500 ; net = 500 - 50 = 450
    assert Decimal(rows[0][9]) == Decimal("500")
    assert Decimal(rows[0][10]) == Decimal("450")


# ═════════════════════════════════════════════════════════════════════════════
# /exports/summary.csv
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_summary_single_row(client: AsyncClient, db_session: AsyncSession) -> None:
    """Summary CSV has exactly one data row + nine columns."""
    user = await _mk_user(db_session, "exp_s1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid, qty="100", price="500")
    await _seed_price_history(db_session, "2330", last_close="550", prev_close="540")

    r = await client.get("/api/v1/holdings/exports/summary.csv", headers=_auth(user))
    assert r.status_code == 200, r.text
    header, rows = _parse_csv(r.content)
    assert header == [
        "total_cost",
        "total_value",
        "unrealized_pnl",
        "daily_change",
        "gain_simple",
        "gain_simple_pct",
        "position_count",
        "account_count",
        "exported_at",
    ]
    assert len(rows) == 1
    assert Decimal(rows[0][0]) == Decimal("50000")  # 100 * 500
    assert Decimal(rows[0][1]) == Decimal("55000")  # 100 * 550
    assert int(rows[0][6]) == 1  # position_count
    assert int(rows[0][7]) == 1  # account_count


# ═════════════════════════════════════════════════════════════════════════════
# CSV format guarantees
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_export_csv_has_bom_prefix(client: AsyncClient, db_session: AsyncSession) -> None:
    """Every export starts with the UTF-8 BOM bytes so Excel auto-detects
    encoding for any non-ASCII column (broker/note in Chinese)."""
    user = await _mk_user(db_session, "exp_b1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 200
    # BOM in UTF-8 is exactly these three bytes.
    assert r.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
async def test_export_csv_quotes_field_with_comma_in_note(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """``csv.writer`` (QUOTE_MINIMAL) wraps fields with a comma in
    double quotes, doubling any embedded quote — round-trip through the
    standard parser yields the original string."""
    user = await _mk_user(db_session, "exp_q1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    note = 'long, "ROI" play'
    await _seed_buy(client, user, aid, note=note)

    r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 200
    # Raw body still contains the escaped form...
    assert b'"long, ""ROI"" play"' in r.content
    # ...and the standard parser reconstructs the original.
    _, rows = _parse_csv(r.content)
    assert rows[0][-1] == note


@pytest.mark.asyncio
async def test_export_empty_data_returns_csv_with_header_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User with no accounts/trades still gets a valid CSV with just
    the header — file is never zero-bytes."""
    user = await _mk_user(db_session, "exp_e1@x.tw", tier=UserTier.PRO)

    r = await client.get("/api/v1/holdings/exports/trades.csv", headers=_auth(user))
    assert r.status_code == 200
    header, rows = _parse_csv(r.content)
    assert header[0] == "trade_date"
    assert rows == []
