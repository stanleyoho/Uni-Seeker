"""Integration tests for ``/api/v1/me/audit-logs`` (Round 13).

Coverage (8 cases):
  - list user's own logs ordered ``created_at DESC``
  - pagination via ``limit`` + ``offset``
  - ``event_types`` whitelist filter
  - empty list when the user has no audit rows
  - cross-user isolation (caller A cannot see caller B's rows)
  - ``limit`` cap enforcement (422 above 500)
  - audit row fields (resource_*, after_state, metadata) preserved
  - 401 when unauthenticated

SQLite ``func.now()`` returns whole-second granularity, so tests that
care about ordering write ``created_at`` explicitly with sub-second
offsets — that exercises the real ``ORDER BY created_at DESC`` path
without depending on insert-time clock resolution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from typing import TYPE_CHECKING

from app.auth import create_access_token
from app.models.audit_log import AuditLog
from app.models.enums import UserTier
from app.models.user import User
from app.services.audit import log_audit_event

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


# ── helpers ──────────────────────────────────────────────────────────────


async def _mk_user(
    db: AsyncSession,
    email: str,
    *,
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


async def _seed_event(
    db: AsyncSession,
    user: User,
    *,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    after_state: dict | None = None,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> AuditLog:
    """Insert one audit row through the canonical helper so the test
    matches production semantics (Prometheus counter, Sentry breadcrumb).

    If ``created_at`` is provided, overwrite the server-default after
    the row is flushed — SQLite's ``func.now()`` is whole-second so
    tests that care about ordering need finer granularity.
    """
    row = await log_audit_event(
        db,
        action=action,
        user_id=user.id,
        resource_type=resource_type,
        resource_id=resource_id,
        after_state=after_state,
        metadata=metadata,
    )
    if created_at is not None:
        row.created_at = created_at
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ── tests ────────────────────────────────────────────────────────────────


async def test_list_my_audit_logs_returns_newest_first(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "audit_order@x.com")
    base = datetime.now(UTC) - timedelta(hours=1)
    # Insert in non-monotonic order to prove the ORDER BY actually sorts.
    await _seed_event(
        db_session, user, action="watchlist_added", created_at=base + timedelta(seconds=2)
    )
    await _seed_event(db_session, user, action="user_login", created_at=base)
    await _seed_event(
        db_session,
        user,
        action="me_notifications_updated",
        created_at=base + timedelta(seconds=5),
    )

    resp = await client.get("/api/v1/me/audit-logs", headers=_auth(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_count"] == 3
    assert body["has_more"] is False
    assert len(body["entries"]) == 3

    event_types = [e["event_type"] for e in body["entries"]]
    assert event_types == [
        "me_notifications_updated",  # base + 5s — newest
        "watchlist_added",  # base + 2s
        "user_login",  # base — oldest
    ]


async def test_list_my_audit_logs_paginates(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "audit_page@x.com")
    base = datetime.now(UTC) - timedelta(hours=1)
    for i in range(5):
        await _seed_event(
            db_session,
            user,
            action=f"event_{i}",
            created_at=base + timedelta(seconds=i),
        )

    # First page
    resp = await client.get("/api/v1/me/audit-logs?limit=2&offset=0", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 5
    assert body["has_more"] is True
    assert len(body["entries"]) == 2
    # Newest two events first.
    assert [e["event_type"] for e in body["entries"]] == [
        "event_4",
        "event_3",
    ]

    # Second page
    resp = await client.get("/api/v1/me/audit-logs?limit=2&offset=2", headers=_auth(user))
    body = resp.json()
    assert body["total_count"] == 5
    assert body["has_more"] is True
    assert len(body["entries"]) == 2

    # Last page — has_more flips to False
    resp = await client.get("/api/v1/me/audit-logs?limit=2&offset=4", headers=_auth(user))
    body = resp.json()
    assert body["total_count"] == 5
    assert body["has_more"] is False
    assert len(body["entries"]) == 1


async def test_list_my_audit_logs_filters_by_event_types(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "audit_filter@x.com")
    await _seed_event(db_session, user, action="user_login")
    await _seed_event(db_session, user, action="watchlist_added")
    await _seed_event(db_session, user, action="watchlist_removed")
    await _seed_event(db_session, user, action="kyc_completed")

    resp = await client.get(
        "/api/v1/me/audit-logs?event_types=watchlist_added&event_types=watchlist_removed",
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_count"] == 2
    types = sorted(e["event_type"] for e in body["entries"])
    assert types == ["watchlist_added", "watchlist_removed"]


async def test_list_my_audit_logs_empty_when_no_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "audit_empty@x.com")

    resp = await client.get("/api/v1/me/audit-logs", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"entries": [], "total_count": 0, "has_more": False}


async def test_list_my_audit_logs_isolates_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    alice = await _mk_user(db_session, "alice@x.com")
    bob = await _mk_user(db_session, "bob@x.com")

    await _seed_event(db_session, alice, action="alice_only")
    await _seed_event(db_session, bob, action="bob_only_1")
    await _seed_event(db_session, bob, action="bob_only_2")

    # Alice sees only her row.
    resp = await client.get("/api/v1/me/audit-logs", headers=_auth(alice))
    body = resp.json()
    assert body["total_count"] == 1
    assert [e["event_type"] for e in body["entries"]] == ["alice_only"]

    # Bob sees only his two rows.
    resp = await client.get("/api/v1/me/audit-logs", headers=_auth(bob))
    body = resp.json()
    assert body["total_count"] == 2
    assert {e["event_type"] for e in body["entries"]} == {
        "bob_only_1",
        "bob_only_2",
    }


async def test_list_my_audit_logs_rejects_excessive_limit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "audit_cap@x.com")

    # 500 is the documented cap — pass.
    resp = await client.get("/api/v1/me/audit-logs?limit=500", headers=_auth(user))
    assert resp.status_code == 200

    # 501 is over the cap — Pydantic Query validation kicks in.
    resp = await client.get("/api/v1/me/audit-logs?limit=501", headers=_auth(user))
    assert resp.status_code == 422


async def test_list_my_audit_logs_preserves_all_fields(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _mk_user(db_session, "audit_fields@x.com")
    after = {"telegram_chat_id": "12345"}
    metadata = {"ip": "10.0.0.1", "ua": "pytest"}
    row = await _seed_event(
        db_session,
        user,
        action="me_notifications_updated",
        resource_type="user",
        resource_id=str(user.id),
        after_state=after,
        metadata=metadata,
    )

    resp = await client.get("/api/v1/me/audit-logs", headers=_auth(user))
    body = resp.json()
    assert body["total_count"] == 1
    entry = body["entries"][0]
    assert entry["id"] == str(row.id)
    assert entry["event_type"] == "me_notifications_updated"
    assert entry["resource_type"] == "user"
    assert entry["resource_id"] == str(user.id)
    assert entry["after_state"] == after
    assert entry["metadata"] == metadata
    # created_at must be present and parseable as ISO string.
    assert isinstance(entry["created_at"], str)
    assert entry["created_at"].startswith(str(row.created_at.year))


async def test_list_my_audit_logs_requires_auth(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/me/audit-logs")
    assert resp.status_code in (401, 403)
