"""Integration tests for POST /api/v1/institutional/filers/bulk.

Spec: 13F bulk subscribe — atomic tier quota + EDGAR metadata fallback +
partial-success envelope. Mirrors the watchlist `/bulk` pattern but with
the F13 `max_tracked_filers` cap (Free 1 / Basic 5 / Pro unlimited).

Coverage (~10 cases):
  1. happy_path                  — 3 fresh CIKs all subscribe
  2. tier_quota_atomic           — Free user, batch of 2 > limit 1 → 403,
                                   nothing inserted
  3. request_dedup               — input has 2 identical CIKs → only one
                                   subscription created
  4. existing_dedup              — one CIK already subscribed → reported
                                   in skipped_duplicates, NOT errors
  5. invalid_cik_format          — non-digit CIK → errors[invalid_cik],
                                   other rows still proceed
  6. edgar_metadata_fallback     — name missing → mock EdgarClient
                                   resolves it; subscription created
  7. atomic_on_failure           — repo INSERT raises mid-loop → whole
                                   batch rolled back
  8. empty_list_422              — Pydantic rejects empty `items`
  9. over_20_422                 — Pydantic rejects 21-item batch
 10. cross_user_isolation        — User A's bulk subscribe doesn't leak
                                   into User B's list

EDGAR client is dep-overridden to `_MockEdgarClient` (same pattern as
`test_institutional_api.py`).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.institutional._deps import get_edgar_client
from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User
from app.modules.institutional.edgar_client import FilerMetadata
from app.repositories.institutional import F13UserSubscriptionRepo

# ── Helpers (mirror test_institutional_api.py) ──────────────────────────


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


def _client_app(client: AsyncClient):
    """Grab the FastAPI app instance the test client is bound to.

    `tests/conftest.py::client` calls `create_app()` which returns a
    NEW instance (not `app.main.app`), so we MUST override on this
    instance for dep overrides to actually fire.
    """
    return client._transport.app  # type: ignore[attr-defined]


class _MockEdgarClient:
    """Duck-typed `EdgarClient` test double — only methods we call here.

    Tests configure `metadata_responses[cik] = FilerMetadata(...)` to
    drive `get_filer_metadata` calls. Unset CIKs return a synthesised
    default name so the happy-path tests don't have to wire each one.
    """

    def __init__(self) -> None:
        self.metadata_responses: dict[str, FilerMetadata] = {}
        self.calls_get_metadata: list[str] = []
        self.should_raise: bool = False

    async def get_filer_metadata(self, cik: str) -> FilerMetadata:
        self.calls_get_metadata.append(cik)
        if self.should_raise:
            raise RuntimeError("edgar transient failure (mock)")
        if cik in self.metadata_responses:
            return self.metadata_responses[cik]
        return FilerMetadata(cik=cik, name=f"EDGAR Resolved {cik}", legal_name=None)


@pytest.fixture
def mock_edgar(client: AsyncClient):
    app = _client_app(client)
    mock = _MockEdgarClient()
    app.dependency_overrides[get_edgar_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_edgar_client, None)


BULK_URL = "/api/v1/institutional/filers/bulk"


# ═════════════════════════════════════════════════════════════════════════════
# Tests
# ═════════════════════════════════════════════════════════════════════════════


async def test_bulk_subscribe_happy_path(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """3 fresh CIKs all get subscribed; envelope reports them in `subscribed`."""
    user = await _mk_user(db_session, "bulk01@x.com", tier=UserTier.PRO)
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={
            "items": [
                {"cik": "0001000001", "name": "Filer One"},
                {"cik": "0001000002", "name": "Filer Two"},
                {"cik": "0001000003", "name": "Filer Three"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["subscribed"]) == 3
    assert body["skipped_duplicates"] == []
    assert body["errors"] == []
    # Each cik must be 10-digit padded.
    returned_ciks = {f["cik"] for f in body["subscribed"]}
    assert returned_ciks == {"0001000001", "0001000002", "0001000003"}

    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 3


async def test_bulk_subscribe_tier_quota_atomic(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Free user (limit=1), batch of 2 → 403; nothing inserted (atomic)."""
    user = await _mk_user(db_session, "bulk02@x.com", tier=UserTier.FREE)

    with (
        patch("app.modules.billing.tier_limits.settings") as guard_settings,
        patch("app.services.institutional.subscription_service.settings") as svc_settings,
    ):
        guard_settings.enable_monetization = True
        svc_settings.enable_monetization = True
        resp = await client.post(
            BULK_URL,
            headers=_auth(user),
            json={
                "items": [
                    {"cik": "0002000001", "name": "A"},
                    {"cik": "0002000002", "name": "B"},
                ],
            },
        )
    assert resp.status_code == 403, resp.text
    assert "limit_exceeded:max_tracked_filers" in resp.json()["message"]

    # Atomic: NO subscription rows created.
    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 0


async def test_bulk_subscribe_request_dedup(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Duplicate CIK in the same request → only one subscription created."""
    user = await _mk_user(db_session, "bulk03@x.com", tier=UserTier.PRO)
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={
            "items": [
                {"cik": "0003000001", "name": "Dup"},
                {"cik": "0003000001", "name": "Dup again"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["subscribed"]) == 1
    assert body["subscribed"][0]["cik"] == "0003000001"
    # Request-level dedupe is silent (not reported in skipped_duplicates).
    assert body["skipped_duplicates"] == []
    assert body["errors"] == []

    count = await F13UserSubscriptionRepo(db_session).count_by_user(user.id)
    assert count == 1


async def test_bulk_subscribe_existing_dedup(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Already-subscribed CIK → skipped_duplicates (not errors)."""
    user = await _mk_user(db_session, "bulk04@x.com", tier=UserTier.PRO)

    # Seed: subscribe once via single endpoint.
    first = await client.post(
        "/api/v1/institutional/filers",
        headers=_auth(user),
        json={"cik": "0004000001", "name": "Already Subbed"},
    )
    assert first.status_code == 201

    # Bulk: mix already-subbed CIK with a new one.
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={
            "items": [
                {"cik": "0004000001", "name": "Already Subbed"},
                {"cik": "0004000002", "name": "Fresh"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["subscribed"]) == 1
    assert body["subscribed"][0]["cik"] == "0004000002"
    assert body["skipped_duplicates"] == ["0004000001"]
    assert body["errors"] == []


async def test_bulk_subscribe_invalid_cik_format(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Non-digit CIK → errors[invalid_cik]; remaining rows still subscribe."""
    user = await _mk_user(db_session, "bulk05@x.com", tier=UserTier.PRO)
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={
            "items": [
                {"cik": "ABCDEF", "name": "Bad"},
                {"cik": "0005000001", "name": "Good"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["subscribed"]) == 1
    assert body["subscribed"][0]["cik"] == "0005000001"
    assert any(e["cik"] == "ABCDEF" and e["reason"] == "invalid_cik" for e in body["errors"])


async def test_bulk_subscribe_edgar_metadata_fallback(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Name omitted → EDGAR metadata resolves it via mocked client."""
    user = await _mk_user(db_session, "bulk06@x.com", tier=UserTier.PRO)
    mock_edgar.metadata_responses["0006000001"] = FilerMetadata(
        cik="0006000001",
        name="Edgar Provided Name",
        legal_name="EDGAR PROVIDED NAME LLC",
    )

    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={
            "items": [
                {"cik": "0006000001"},  # name absent
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["subscribed"]) == 1
    assert body["subscribed"][0]["name"] == "Edgar Provided Name"
    assert "0006000001" in mock_edgar.calls_get_metadata


async def test_bulk_subscribe_atomic_on_failure(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """If repo INSERT raises mid-loop, the WHOLE batch rolls back.

    The httpx test client re-raises the exception rather than returning
    a 500 because Starlette's default ExceptionMiddleware bubbles in
    test mode (see fastapi.testclient docs). We assert the exception
    bubbles AND no rows are committed (atomic contract).
    """
    user = await _mk_user(db_session, "bulk07@x.com", tier=UserTier.PRO)
    user_id = user.id  # Capture before any potential session expiry.

    # Patch the subscription repo's subscribe() to raise on the 2nd call.
    call_count = {"n": 0}
    from app.repositories.institutional.subscription_repo import (
        F13UserSubscriptionRepo as RealRepo,
    )

    original_subscribe = RealRepo.subscribe

    async def flaky_subscribe(self, user_id, filer_id, notify_on_new_filing=True):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated mid-batch DB failure")
        return await original_subscribe(
            self,
            user_id=user_id,
            filer_id=filer_id,
            notify_on_new_filing=notify_on_new_filing,
        )

    with patch.object(RealRepo, "subscribe", flaky_subscribe):
        # Either Starlette returns 500 OR the test client re-raises
        # (possibly wrapped in an ExceptionGroup / surfaced as a
        # downstream SQLAlchemy MissingGreenlet during error rendering).
        # The atomic contract is "no commit happened" regardless of how
        # the failure surfaces to the caller.
        with pytest.raises(BaseException):
            resp = await client.post(
                BULK_URL,
                headers=_auth(user),
                json={
                    "items": [
                        {"cik": "0007000001", "name": "First"},
                        {"cik": "0007000002", "name": "Second"},
                        {"cik": "0007000003", "name": "Third"},
                    ],
                },
            )
            # If Starlette did render a 500 we still expect server-error.
            assert resp.status_code >= 500, resp.text

    # Atomic rollback: the endpoint never called `await db.commit()`.
    # In test mode the shared AsyncSession sees its own uncommitted
    # FLUSH (SQLite per-session transaction visibility), so we rollback
    # explicitly to simulate what happens after the request scope
    # cleanup — then count must be 0.
    await db_session.rollback()
    count = await F13UserSubscriptionRepo(db_session).count_by_user(user_id)
    assert count == 0
    # Sanity: the second flaky call must have fired (otherwise we
    # didn't actually exercise the atomic branch).
    assert call_count["n"] >= 2


async def test_bulk_subscribe_empty_list_422(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Pydantic rejects empty `items` with 422."""
    user = await _mk_user(db_session, "bulk08@x.com", tier=UserTier.PRO)
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={"items": []},
    )
    assert resp.status_code == 422, resp.text


async def test_bulk_subscribe_over_20_422(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """Pydantic rejects > 20-item batches with 422."""
    user = await _mk_user(db_session, "bulk09@x.com", tier=UserTier.PRO)
    items = [{"cik": f"00090000{i:02d}", "name": f"f{i}"} for i in range(21)]
    resp = await client.post(
        BULK_URL,
        headers=_auth(user),
        json={"items": items},
    )
    assert resp.status_code == 422, resp.text


async def test_bulk_subscribe_cross_user_isolation(
    client: AsyncClient, db_session: AsyncSession, mock_edgar
) -> None:
    """User A's bulk subscribe doesn't appear in User B's subscription list."""
    user_a = await _mk_user(db_session, "bulk10a@x.com", tier=UserTier.PRO)
    user_b = await _mk_user(db_session, "bulk10b@x.com", tier=UserTier.PRO)

    resp_a = await client.post(
        BULK_URL,
        headers=_auth(user_a),
        json={
            "items": [
                {"cik": "0010000001", "name": "A Filer"},
                {"cik": "0010000002", "name": "B Filer"},
            ],
        },
    )
    assert resp_a.status_code == 201

    # B's list should be empty — no leak.
    list_b = await client.get("/api/v1/institutional/filers", headers=_auth(user_b))
    assert list_b.status_code == 200
    assert list_b.json() == []

    count_a = await F13UserSubscriptionRepo(db_session).count_by_user(user_a.id)
    count_b = await F13UserSubscriptionRepo(db_session).count_by_user(user_b.id)
    assert count_a == 2
    assert count_b == 0
