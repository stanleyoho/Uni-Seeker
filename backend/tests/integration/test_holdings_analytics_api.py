"""Integration tests for /api/v1/holdings/analytics — Phase 5.

Covers the end-to-end HTTP path:
  N01 1m happy path returns AnalyticsResponse
  N02 FREE tier → 403 feature_unavailable:daily_change_breakdown
  N03 BASIC tier → 403 (basic also lacks the proxy feature)
  N04 insufficient snapshots (<2) → 200 with snapshot_count<2 and sharpe=None
  N05 account_id filter scopes to that account
  N06 account_id not owned → 404 portfolio_account_not_found
  N07 period boundary: snapshots outside the period are excluded
  N08 empty data (no snapshots) → 200, all zeros, sharpe=None
  N09 cross-user isolation — user B cannot see user A's snapshots
  N10 Decimal-as-string contract on the wire
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.db.models.portfolio import HoldingsSnapshot, PortfolioAccount
from app.models.enums import Market, UserTier
from app.models.user import User

if TYPE_CHECKING:
    pass


def _auth(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.email)}"
    }


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


async def _mk_account(
    db: AsyncSession, user_id: int, name: str = "AAcc",
) -> PortfolioAccount:
    acc = PortfolioAccount(user_id=user_id, name=name, market=Market.TW_TWSE)
    db.add(acc)
    await db.commit()
    await db.refresh(acc)
    return acc


async def _add_snap(
    db: AsyncSession,
    user_id: int,
    snapshot_date: date,
    total_value: str,
    *,
    account_id: int | None = None,
    total_cost: str = "100",
    position_count: int = 1,
) -> None:
    db.add(HoldingsSnapshot(
        user_id=user_id,
        snapshot_date=snapshot_date,
        total_value=Decimal(total_value),
        total_cost=Decimal(total_cost),
        total_unrealized_pnl=Decimal(total_value) - Decimal(total_cost),
        realized_pnl_cum=Decimal("0"),
        position_count=position_count,
        account_id=account_id,
    ))
    await db.commit()


# ─────────────────────────────────────────────────────────────────────
# N01 — happy path, 1m period (default), PRO tier
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N01_happy_path_returns_analytics(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "n1@x.tw")
    today = date.today()
    # Seed 3 user-wide snapshots within the 30-day window.
    await _add_snap(db_session, user.id, today - __import__("datetime").timedelta(days=20), "100")
    await _add_snap(db_session, user.id, today - __import__("datetime").timedelta(days=10), "110")
    await _add_snap(db_session, user.id, today, "115")

    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Body shape contract.
    assert "twr" in body
    assert "twr_annualized" in body
    assert "sharpe_ratio" in body
    assert "max_drawdown" in body
    assert "max_drawdown_pct" in body
    assert "period_days" in body
    assert "snapshot_count" in body
    assert body["snapshot_count"] == 3
    # twr ≈ 0.15 (100 → 115 with no flows)
    assert Decimal(body["twr"]) == Decimal("0.15")


# ─────────────────────────────────────────────────────────────────────
# N02 — FREE tier → 403
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N02_free_tier_blocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "n2@x.tw", tier=UserTier.FREE)
    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 403
    assert r.json()["message"] == "feature_unavailable:daily_change_breakdown"


# ─────────────────────────────────────────────────────────────────────
# N03 — BASIC tier also blocked (proxy feature is Pro-only)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N03_basic_tier_blocked(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "n3@x.tw", tier=UserTier.BASIC)
    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 403
    assert r.json()["message"] == "feature_unavailable:daily_change_breakdown"


# ─────────────────────────────────────────────────────────────────────
# N04 — insufficient snapshots (1 row only) → 200 with sharpe=None
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N04_insufficient_snapshots(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "n4@x.tw")
    await _add_snap(db_session, user.id, date.today(), "100")
    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_count"] == 1
    assert body["sharpe_ratio"] is None
    assert Decimal(body["twr"]) == Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# N05 — account_id filter scopes to that account
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N05_account_id_filter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import timedelta
    user = await _mk_user(db_session, "n5@x.tw")
    acc_a = await _mk_account(db_session, user.id, "AccA")
    acc_b = await _mk_account(db_session, user.id, "AccB")
    today = date.today()
    # Two snapshots for A within window
    await _add_snap(
        db_session, user.id, today - timedelta(days=10), "100",
        account_id=acc_a.id,
    )
    await _add_snap(
        db_session, user.id, today, "150", account_id=acc_a.id,
    )
    # B has different numbers in the same period
    await _add_snap(
        db_session, user.id, today - timedelta(days=10), "200",
        account_id=acc_b.id,
    )
    await _add_snap(
        db_session, user.id, today, "210", account_id=acc_b.id,
    )

    r_a = await client.get(
        f"/api/v1/holdings/analytics?account_id={acc_a.id}",
        headers=_auth(user),
    )
    assert r_a.status_code == 200
    assert r_a.json()["snapshot_count"] == 2
    # A: 100 → 150, TWR = 0.5
    assert Decimal(r_a.json()["twr"]) == Decimal("0.5")

    r_b = await client.get(
        f"/api/v1/holdings/analytics?account_id={acc_b.id}",
        headers=_auth(user),
    )
    assert r_b.status_code == 200
    # B: 200 → 210, TWR = 0.05
    assert Decimal(r_b.json()["twr"]) == Decimal("0.05")


# ─────────────────────────────────────────────────────────────────────
# N06 — unowned account_id → 404
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N06_unowned_account_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    a = await _mk_user(db_session, "n6a@x.tw")
    b = await _mk_user(db_session, "n6b@x.tw")
    acc = await _mk_account(db_session, a.id, "Aown")
    r = await client.get(
        f"/api/v1/holdings/analytics?account_id={acc.id}",
        headers=_auth(b),
    )
    assert r.status_code == 404
    assert r.json()["message"] == "portfolio_account_not_found"


# ─────────────────────────────────────────────────────────────────────
# N07 — snapshots outside the 1m window are excluded
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N07_period_boundary_excludes_old_snapshots(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import timedelta
    user = await _mk_user(db_session, "n7@x.tw")
    today = date.today()
    # OLD: 90 days ago — falls OUTSIDE 1m (30 day) window.
    await _add_snap(db_session, user.id, today - timedelta(days=90), "1")
    # IN-WINDOW: 5 days ago + today.
    await _add_snap(db_session, user.id, today - timedelta(days=5), "100")
    await _add_snap(db_session, user.id, today, "110")

    r = await client.get(
        "/api/v1/holdings/analytics?period=1m", headers=_auth(user),
    )
    assert r.status_code == 200
    body = r.json()
    # Only 2 in-window rows.
    assert body["snapshot_count"] == 2
    assert Decimal(body["twr"]) == Decimal("0.1")


# ─────────────────────────────────────────────────────────────────────
# N08 — empty data still returns 200 with all-zero result, sharpe=None
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N08_empty_data_returns_zeros(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "n8@x.tw")
    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_count"] == 0
    assert body["sharpe_ratio"] is None
    assert Decimal(body["twr"]) == Decimal("0")
    assert Decimal(body["max_drawdown"]) == Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# N09 — cross-user isolation
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N09_cross_user_isolation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import timedelta
    a = await _mk_user(db_session, "n9a@x.tw")
    b = await _mk_user(db_session, "n9b@x.tw")
    today = date.today()
    # A has 2 snapshots
    await _add_snap(db_session, a.id, today - timedelta(days=10), "100")
    await _add_snap(db_session, a.id, today, "200")
    # B has none
    r_b = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(b),
    )
    assert r_b.status_code == 200
    assert r_b.json()["snapshot_count"] == 0


# ─────────────────────────────────────────────────────────────────────
# N10 — Decimal-as-string contract
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_N10_decimal_as_string_on_wire(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import timedelta
    user = await _mk_user(db_session, "n10@x.tw")
    today = date.today()
    await _add_snap(db_session, user.id, today - timedelta(days=10), "100")
    await _add_snap(db_session, user.id, today, "110")
    r = await client.get(
        "/api/v1/holdings/analytics", headers=_auth(user),
    )
    assert r.status_code == 200
    body = r.json()
    # twr, twr_annualized, max_drawdown, max_drawdown_pct must be strings.
    assert isinstance(body["twr"], str)
    assert isinstance(body["twr_annualized"], str)
    assert isinstance(body["max_drawdown"], str)
    assert isinstance(body["max_drawdown_pct"], str)
    # sharpe_ratio is None or string
    if body["sharpe_ratio"] is not None:
        assert isinstance(body["sharpe_ratio"], str)
