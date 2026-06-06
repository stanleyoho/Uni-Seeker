"""Integration tests for /api/v1/holdings/dividends/* — Portfolio Tracker
Phase 2 Batch C.

Spec §5.4 Table 3 + §9 + §13 AC matrix. ~17 cases covering:

- POST happy path for CASH + STOCK + BASIC + PRO tiers
- POST FREE tier → 403 ``feature_unavailable:dividends`` (dependency-
  layer first line of the spec §9 雙保險)
- POST invalid dividend type → 422 ``invalid_dividend_input``
- POST unknown / cross-user account → 404 ``portfolio_account_not_found``
- GET list (user-scoped, account filter, pagination)
- GET by id (200, 404 cross-user)
- PATCH allowed fields (note / pay_date / withholding_tax) → 200
- PATCH immutable field (amount_per_share / dividend_type) → 422
  ``immutable_dividend_field``
- DELETE → 204; cross-user DELETE → 404
- Decimal-as-string serialization assertion on the POST response body

Mirrors `test_holdings_api.py` conventions (`_mk_user`, `_auth`,
`_create_account_via_api`) so reviewer cognitive load stays low.
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
) -> None:
    """Drop a BUY trade so the dividend has a position + lots to act on."""
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


def _cash_body(aid: int, **overrides) -> dict:
    body = {
        "account_id": aid,
        "symbol": "2330",
        "market": "TW_TWSE",
        "dividend_type": "CASH",
        "ex_dividend_date": "2026-05-10",
        "pay_date": "2026-06-01",
        "amount_per_share": "5",
        "quantity_at_record": "100",
        "withholding_tax": "50",
        "currency": "TWD",
    }
    body.update(overrides)
    return body


def _stock_body(aid: int, **overrides) -> dict:
    body = {
        "account_id": aid,
        "symbol": "2330",
        "market": "TW_TWSE",
        "dividend_type": "STOCK",
        "ex_dividend_date": "2026-05-10",
        "quantity_at_record": "100",
        "ratio": "0.25",
        "currency": "TWD",
    }
    body.update(overrides)
    return body


# ═════════════════════════════════════════════════════════════════════════════
# POST /holdings/dividends
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_cash_dividend_pro_user_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PRO tier records a CASH dividend; body comes back enriched with
    total_amount / net_amount."""
    user = await _mk_user(db_session, "div_c1@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dividend_type"] == "CASH"
    assert body["symbol"] == "2330"
    assert body["id"] is not None
    # total = 100 * 5 = 500; net = 500 - 50 = 450
    assert Decimal(body["total_amount"]) == Decimal("500")
    assert Decimal(body["net_amount"]) == Decimal("450")


# ═════════════════════════════════════════════════════════════════════════════
# GET /holdings/dividends/monthly-summary  (K4 婆媽 widget)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_monthly_summary_route_resolves_before_id_param(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`monthly-summary` must hit the dedicated handler, NOT be parsed as
    an int `dividend_id` (which would 422). Empty portfolio → zeros."""
    user = await _mk_user(db_session, "div_ms1@x.tw")
    r = await client.get("/api/v1/holdings/dividends/monthly-summary", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "month",
        "gross_amount",
        "net_amount",
        "cash_count",
        "stock_count",
    }
    # Decimal-as-string contract on the money fields.
    assert isinstance(body["gross_amount"], str)
    assert isinstance(body["net_amount"], str)
    assert Decimal(body["gross_amount"]) == Decimal("0")
    assert body["cash_count"] == 0
    assert body["stock_count"] == 0


@pytest.mark.asyncio
async def test_monthly_summary_counts_cash_excludes_stock_money(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """End-to-end: a CASH + a STOCK dividend recorded this month — money
    reflects CASH only, stock_count reflects the 配股 row."""
    import datetime as _dt

    today = _dt.date.today()
    user = await _mk_user(db_session, "div_ms2@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    # CASH this month, pay_date today → 5×100 = 500 gross, 50 tax → 450 net
    rc = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(
            aid,
            ex_dividend_date=today.isoformat(),
            pay_date=today.isoformat(),
        ),
        headers=_auth(user),
    )
    assert rc.status_code == 201, rc.text
    # STOCK this month → must NOT add to money, only stock_count.
    rs = await client.post(
        "/api/v1/holdings/dividends",
        json=_stock_body(
            aid,
            ex_dividend_date=today.isoformat(),
            pay_date=today.isoformat(),
        ),
        headers=_auth(user),
    )
    assert rs.status_code == 201, rs.text

    r = await client.get("/api/v1/holdings/dividends/monthly-summary", headers=_auth(user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["gross_amount"]) == Decimal("500")
    assert Decimal(body["net_amount"]) == Decimal("450")
    assert body["cash_count"] == 1
    assert body["stock_count"] == 1
    assert body["month"] == today.strftime("%Y-%m")


@pytest.mark.asyncio
async def test_create_stock_dividend_pro_user_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PRO tier records a STOCK dividend at ratio=0.25; the response
    body's `amount_per_share` carries the ratio (service stores it
    there)."""
    user = await _mk_user(db_session, "div_c2@x.tw", tier=UserTier.PRO)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_stock_body(aid),
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dividend_type"] == "STOCK"
    # Service stores ratio in amount_per_share (CHECK > 0).
    assert Decimal(body["amount_per_share"]) == Decimal("0.25")
    # And appends "ratio=0.25" to note for forensic clarity.
    assert "ratio=0.25" in (body["note"] or "")


@pytest.mark.asyncio
async def test_create_dividend_free_user_403_feature_unavailable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier hits the dependency-layer `tier_guard(feature='dividends')`
    and gets 403 BEFORE any DB write."""
    user = await _mk_user(db_session, "div_c3@x.tw", tier=UserTier.FREE)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    with (
        patch("app.modules.billing.tier_limits.settings") as s_tg,
        patch("app.services.portfolio.dividend_service.settings") as s_svc,
    ):
        s_tg.enable_monetization = True
        s_svc.enable_monetization = True
        r = await client.post(
            "/api/v1/holdings/dividends",
            json=_cash_body(aid),
            headers=_auth(user),
        )
    assert r.status_code == 403, r.text
    assert r.json()["message"] == "feature_unavailable:dividends"


@pytest.mark.asyncio
async def test_create_dividend_basic_user_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """BASIC tier has dividends=true → CASH record succeeds with
    monetization on."""
    user = await _mk_user(db_session, "div_c4@x.tw", tier=UserTier.BASIC)
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)

    with (
        patch("app.modules.billing.tier_limits.settings") as s_tg,
        patch("app.services.portfolio.dividend_service.settings") as s_svc,
    ):
        s_tg.enable_monetization = True
        s_svc.enable_monetization = True
        r = await client.post(
            "/api/v1/holdings/dividends",
            json=_cash_body(aid, amount_per_share="2"),
            headers=_auth(user),
        )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_create_dividend_invalid_type_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A `dividend_type` outside CASH/STOCK is rejected by Pydantic at the
    DTO layer with a 422 (FastAPI's default validation error envelope)."""
    user = await _mk_user(db_session, "div_c5@x.tw")
    aid = await _create_account_via_api(client, user)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid, dividend_type="BOGUS"),
        headers=_auth(user),
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_create_dividend_missing_amount_for_cash_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """CASH dividend without `amount_per_share` slips past Pydantic (the
    field is Optional in the DTO so both branches share one schema) and
    hits the service's ValueError → 422 ``invalid_dividend_input``.
    This is the dedicated branch the endpoint's ValueError→422 mapper
    was written for."""
    user = await _mk_user(db_session, "div_c5b@x.tw")
    aid = await _create_account_via_api(client, user)
    body = _cash_body(aid)
    body.pop("amount_per_share")
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=body,
        headers=_auth(user),
    )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "invalid_dividend_input"


@pytest.mark.asyncio
async def test_create_dividend_unknown_account_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "div_c6@x.tw")
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(99999),
        headers=_auth(user),
    )
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


@pytest.mark.asyncio
async def test_create_dividend_cross_user_account_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User B cannot record a dividend on User A's account."""
    a = await _mk_user(db_session, "div_c7a@x.tw")
    b = await _mk_user(db_session, "div_c7b@x.tw")
    aid_a = await _create_account_via_api(client, a)
    await _seed_buy(client, a, aid_a)

    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid_a),
        headers=_auth(b),
    )
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


# ═════════════════════════════════════════════════════════════════════════════
# GET /holdings/dividends
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_dividends_basic_user_200(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "div_l1@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    for i in range(3):
        body = _cash_body(aid, ex_dividend_date=f"2026-05-1{i}")
        await client.post("/api/v1/holdings/dividends", json=body, headers=_auth(user))

    r = await client.get("/api/v1/holdings/dividends", headers=_auth(user))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 3


@pytest.mark.asyncio
async def test_list_dividends_filter_by_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`?account_id=` scopes the list. The other account's row is
    excluded."""
    user = await _mk_user(db_session, "div_l2@x.tw")
    a1 = await _create_account_via_api(client, user, name="a1")
    a2 = await _create_account_via_api(client, user, name="a2")
    await _seed_buy(client, user, a1, symbol="A")
    await _seed_buy(client, user, a2, symbol="B")
    await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(a1, symbol="A"),
        headers=_auth(user),
    )
    await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(a2, symbol="B"),
        headers=_auth(user),
    )

    r1 = await client.get(f"/api/v1/holdings/dividends?account_id={a1}", headers=_auth(user))
    assert r1.status_code == 200
    rows = r1.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "A"


@pytest.mark.asyncio
async def test_list_dividends_pagination(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "div_l3@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    for i in range(5):
        body = _cash_body(aid, ex_dividend_date=f"2026-05-1{i}")
        await client.post("/api/v1/holdings/dividends", json=body, headers=_auth(user))

    r = await client.get("/api/v1/holdings/dividends?limit=2&offset=0", headers=_auth(user))
    assert r.status_code == 200
    assert len(r.json()) == 2

    r2 = await client.get("/api/v1/holdings/dividends?limit=2&offset=4", headers=_auth(user))
    assert r2.status_code == 200
    assert len(r2.json()) == 1  # 5 total - offset 4 = 1 row left


@pytest.mark.asyncio
async def test_get_dividend_by_id_200(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "div_g1@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    did = r.json()["id"]

    rg = await client.get(f"/api/v1/holdings/dividends/{did}", headers=_auth(user))
    assert rg.status_code == 200, rg.text
    assert rg.json()["id"] == did


@pytest.mark.asyncio
async def test_get_dividend_cross_user_404(client: AsyncClient, db_session: AsyncSession) -> None:
    a = await _mk_user(db_session, "div_g2a@x.tw")
    b = await _mk_user(db_session, "div_g2b@x.tw")
    aid_a = await _create_account_via_api(client, a)
    await _seed_buy(client, a, aid_a)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid_a),
        headers=_auth(a),
    )
    did = r.json()["id"]

    rg = await client.get(f"/api/v1/holdings/dividends/{did}", headers=_auth(b))
    assert rg.status_code == 404
    assert rg.json()["message"] == "portfolio_dividend_not_found"


# ═════════════════════════════════════════════════════════════════════════════
# PATCH /holdings/dividends/{id}
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_patch_dividend_allowed_fields_200(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH note + pay_date + withholding_tax succeeds; other fields are
    skipped because the body only sends what changed (model_dump
    exclude_unset)."""
    user = await _mk_user(db_session, "div_p1@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    did = r.json()["id"]

    rp = await client.patch(
        f"/api/v1/holdings/dividends/{did}",
        json={
            "note": "annotated by user",
            "pay_date": "2026-07-01",
            "withholding_tax": "75",
        },
        headers=_auth(user),
    )
    assert rp.status_code == 200, rp.text
    body = rp.json()
    assert body["note"] == "annotated by user"
    assert body["pay_date"] == "2026-07-01"
    assert Decimal(body["withholding_tax"]) == Decimal("75")
    # net_amount re-derived from new withholding_tax: 100*5 - 75 = 425
    assert Decimal(body["net_amount"]) == Decimal("425")


@pytest.mark.asyncio
async def test_patch_dividend_immutable_field_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH an immutable column → service raises ValueError → 422 with
    `immutable_dividend_field` detail."""
    user = await _mk_user(db_session, "div_p2@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    did = r.json()["id"]

    rp = await client.patch(
        f"/api/v1/holdings/dividends/{did}",
        json={"amount_per_share": "99"},
        headers=_auth(user),
    )
    assert rp.status_code == 422, rp.text
    assert rp.json()["message"] == "immutable_dividend_field"


# ═════════════════════════════════════════════════════════════════════════════
# DELETE /holdings/dividends/{id}
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_dividend_204(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "div_d1@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    did = r.json()["id"]

    rd = await client.delete(f"/api/v1/holdings/dividends/{did}", headers=_auth(user))
    assert rd.status_code == 204, rd.text
    # Re-fetch → 404
    rg = await client.get(f"/api/v1/holdings/dividends/{did}", headers=_auth(user))
    assert rg.status_code == 404


@pytest.mark.asyncio
async def test_delete_dividend_cross_user_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    a = await _mk_user(db_session, "div_d2a@x.tw")
    b = await _mk_user(db_session, "div_d2b@x.tw")
    aid_a = await _create_account_via_api(client, a)
    await _seed_buy(client, a, aid_a)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid_a),
        headers=_auth(a),
    )
    did = r.json()["id"]

    rd = await client.delete(f"/api/v1/holdings/dividends/{did}", headers=_auth(b))
    assert rd.status_code == 404
    assert rd.json()["message"] == "portfolio_dividend_not_found"


# ═════════════════════════════════════════════════════════════════════════════
# Wire-format guarantees
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_decimal_as_string_serialization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST returns Decimal columns as JSON strings (CLAUDE.md
    Decimal-as-string contract) — `amount_per_share`,
    `quantity_at_record`, `withholding_tax`, and the computed
    `total_amount` / `net_amount`. We compare value via Decimal because
    SQLA Numeric(24,8) hands back trailing-zero formatted strings."""
    user = await _mk_user(db_session, "div_w1@x.tw")
    aid = await _create_account_via_api(client, user)
    await _seed_buy(client, user, aid)
    r = await client.post(
        "/api/v1/holdings/dividends",
        json=_cash_body(aid),
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    for key in (
        "amount_per_share",
        "quantity_at_record",
        "withholding_tax",
        "total_amount",
        "net_amount",
    ):
        assert isinstance(body[key], str), f"{key} not str: {body[key]!r}"
    assert Decimal(body["amount_per_share"]) == Decimal("5")
    assert Decimal(body["quantity_at_record"]) == Decimal("100")
    assert Decimal(body["withholding_tax"]) == Decimal("50")
    assert Decimal(body["total_amount"]) == Decimal("500")
    assert Decimal(body["net_amount"]) == Decimal("450")
