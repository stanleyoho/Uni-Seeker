"""Integration tests for /api/v1/holdings/imports/csv — Phase 4.

Spec §11 extensibility hook tests. Mirrors the conventions established
in `test_holdings_api.py`:

* `_mk_user` builds a User row with a configurable tier.
* `_auth` produces the bearer header used by every request.
* CSV bodies are posted as raw text/csv (NOT multipart) so we don't
  pull in python-multipart as a new dependency.
* Decimal-as-string is enforced on the wire; numeric comparisons go
  through Decimal.
"""

from __future__ import annotations

from unittest.mock import patch

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


async def _create_account_via_api(client: AsyncClient, user: User, name: str = "Yuanta") -> int:
    r = await client.post(
        "/api/v1/holdings/accounts",
        json={"name": name, "market": "TW_TWSE", "broker": "Yuanta"},
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _csv(rows: list[str]) -> bytes:
    """Build a raw CSV body (header + data rows) as UTF-8 bytes."""
    header = "trade_date,action,symbol,market,quantity,price,fee,tax,note"
    return "\n".join([header, *rows]).encode("utf-8")


async def _trade_count(db: AsyncSession, user_id: int) -> int:
    """Count actual PortfolioTrade rows owned by `user_id`.

    Trades carry only `account_id`; ownership lives on the parent
    `portfolio_accounts.user_id`, so we JOIN to filter.
    """
    return (
        await db.scalar(
            select(func.count())
            .select_from(PortfolioTrade)
            .join(
                PortfolioAccount,
                PortfolioAccount.id == PortfolioTrade.account_id,
            )
            .where(PortfolioAccount.user_id == user_id)
        )
        or 0
    )


# ── 1. dry_run parses without DB write ─────────────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_parses_without_db_write(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "csv1@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-02,BUY,2454,TW_TWSE,5,1000,0,0,",
            "2026-05-03,SELL,2330,TW_TWSE,5,600,0,0,",
        ]
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=true",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["dry_run"] is True
    assert resp["parsed_rows"] == 3
    assert resp["successful_rows"] == 3
    assert resp["failed_rows"] == 0
    assert resp["errors"] == []
    # No trades persisted.
    assert await _trade_count(db_session, uid) == 0


# ── 2. commit writes all rows ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_commit_writes_all_rows(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "csv2@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-02,BUY,2454,TW_TWSE,5,1000,0,0,",
            "2026-05-03,SELL,2330,TW_TWSE,5,600,0,0,",
        ]
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["dry_run"] is False
    assert resp["successful_rows"] == 3
    assert resp["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 3


# ── 3. invalid action — atomic rollback ────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_action_row_reported_and_no_commit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "csv3@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-02,FOO,2330,TW_TWSE,10,500,0,0,",
        ]
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["failed_rows"] == 1
    assert resp["successful_rows"] == 0  # atomic
    assert resp["errors"][0]["error"] == "invalid_action"
    assert resp["errors"][0]["row_index"] == 3
    assert await _trade_count(db_session, uid) == 0


# ── 4. invalid quantity zero ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_quantity_zero_reported(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "csv4@x.tw")
    aid = await _create_account_via_api(client, user)
    body = _csv(["2026-05-01,BUY,2330,TW_TWSE,0,500,0,0,"])
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["failed_rows"] == 1
    assert resp["errors"][0]["error"] == "invalid_quantity"


# ── 5. missing header → 422 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_header_returns_422(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "csv5@x.tw")
    aid = await _create_account_via_api(client, user)
    # Wrong header (missing trailing columns) — file is otherwise valid
    # CSV so we reach the parser, which 422s on the malformed header.
    body = b"trade_date,action,symbol\n2026-05-01,BUY,2330\n"
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 422, r.text
    assert r.json()["message"] == "invalid_csv_format"


# ── 6. body > 1 MiB → 413 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csv_too_large_returns_413(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "csv6@x.tw")
    aid = await _create_account_via_api(client, user)
    header = b"trade_date,action,symbol,market,quantity,price,fee,tax,note\n"
    row = b"2026-05-01,BUY,2330,TW_TWSE,1,1,0,0,\n"
    body = header + row * ((1_500_000 // len(row)) + 1)
    assert len(body) > 1_048_576
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 413, r.text
    assert r.json()["message"] == "csv_too_large"


# ── 7. account not owned → 404 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_account_not_owned_returns_404(client: AsyncClient, db_session: AsyncSession) -> None:
    a = await _mk_user(db_session, "csv7a@x.tw")
    b = await _mk_user(db_session, "csv7b@x.tw")
    aid_a = await _create_account_via_api(client, a)
    body = _csv(["2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,"])
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid_a}",
        content=body,
        headers=_csv_headers(b),
    )
    assert r.status_code == 404, r.text
    assert r.json()["message"] == "portfolio_account_not_found"


# ── 8. tier quota exceeded → 403 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier_quota_exceeded_returns_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """FREE tier: max_trades_per_month=30.

    Pretend the user already has 29 trades this month, then upload a
    3-row CSV; pre-flight quota check fires (29 + 3 > 30) and the
    endpoint 403s with `limit_exceeded:max_trades_per_month`.
    """
    user = await _mk_user(db_session, "csv8@x.tw", tier=UserTier.FREE)
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,1,100,0,0,",
            "2026-05-02,BUY,2330,TW_TWSE,1,100,0,0,",
            "2026-05-03,BUY,2330,TW_TWSE,1,100,0,0,",
        ]
    )
    with (
        patch("app.services.portfolio.import_service.settings") as s_imp,
        patch("app.services.portfolio.trade_service.settings") as s_svc,
        patch("app.modules.billing.tier_limits.settings") as s_tg,
        patch(
            "app.repositories.portfolio.trade_repo.PortfolioTradeRepo.count_by_user_this_month",
            return_value=29,
        ),
    ):
        s_imp.enable_monetization = True
        s_svc.enable_monetization = True
        s_tg.enable_monetization = True
        r = await client.post(
            f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
            content=body,
            headers=_csv_headers(user),
        )
        assert r.status_code == 403, r.text
        assert r.json()["message"] == "limit_exceeded:max_trades_per_month"
    assert await _trade_count(db_session, uid) == 0


# ── 9. partial failure → atomic rollback (2 valid + 1 invalid) ────────────


@pytest.mark.asyncio
async def test_partial_failure_atomic_rollback(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "csv9@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-02,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-03,SELL,2330,TW_TWSE,-5,500,0,0,",
        ]
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["failed_rows"] == 1
    assert resp["successful_rows"] == 0
    assert await _trade_count(db_session, uid) == 0


# ── 10. dry_run does not consume quota ────────────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_does_not_consume_quota(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A dry-run with 30 rows must NOT push the FREE-tier user over
    the monthly quota (the rows aren't real)."""
    user = await _mk_user(db_session, "csv10@x.tw", tier=UserTier.FREE)
    uid = user.id
    aid = await _create_account_via_api(client, user)
    rows = [f"2026-05-{(i % 28) + 1:02d},BUY,2330,TW_TWSE,1,100,0,0," for i in range(30)]
    body = _csv(rows)
    with (
        patch("app.services.portfolio.import_service.settings") as s_imp,
        patch("app.services.portfolio.trade_service.settings") as s_svc,
        patch("app.modules.billing.tier_limits.settings") as s_tg,
    ):
        s_imp.enable_monetization = True
        s_svc.enable_monetization = True
        s_tg.enable_monetization = True
        r = await client.post(
            f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=true",
            content=body,
            headers=_csv_headers(user),
        )
        assert r.status_code == 200, r.text
        resp = r.json()
        assert resp["dry_run"] is True
        assert resp["parsed_rows"] == 30
        assert resp["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 0


# ── 11. DIVIDEND / SPLIT rows rejected with explicit error ─────────────────


@pytest.mark.asyncio
async def test_csv_with_dividend_action_skipped_or_errored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Strategy: REJECT (not silent skip).

    A user uploading a broker CSV that includes dividend rows expects
    feedback. Silently dropping them would make the user think the
    import was complete; reporting them as errored rows forces an
    explicit fix (filter the CSV → re-upload, or use the dedicated
    /holdings/dividends endpoint).
    """
    user = await _mk_user(db_session, "csv11@x.tw")
    aid = await _create_account_via_api(client, user)
    body = _csv(
        [
            "2026-05-01,BUY,2330,TW_TWSE,10,500,0,0,",
            "2026-05-02,DIVIDEND,2330,TW_TWSE,10,5,0,0,",
        ]
    )
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=true",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["failed_rows"] == 1
    assert resp["errors"][0]["error"] == "dividend_actions_not_supported"


# ── 12. empty CSV → zero imported ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_csv_returns_zero_imported(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "csv12@x.tw")
    uid = user.id
    aid = await _create_account_via_api(client, user)
    body = _csv([])
    r = await client.post(
        f"/api/v1/holdings/imports/csv?account_id={aid}&dry_run=false",
        content=body,
        headers=_csv_headers(user),
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["parsed_rows"] == 0
    assert resp["successful_rows"] == 0
    assert resp["failed_rows"] == 0
    assert await _trade_count(db_session, uid) == 0
