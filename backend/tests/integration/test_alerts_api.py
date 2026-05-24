"""Integration tests for /api/v1/holdings/alerts/* (UNI-ALERT-001)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.holdings._deps import get_live_price_fetcher
from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User
from app.modules.portfolio.live_price_fetcher import PriceQuote


class _MockFetcher:
    def __init__(self, quotes: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        self._quotes = quotes or {}

    async def fetch_quotes(
        self, stock_ids: list[str]
    ) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sid in stock_ids:
            if sid in self._quotes:
                last, prev = self._quotes[sid]
                out[sid] = PriceQuote(
                    stock_id=sid,
                    last_price=last,
                    prev_close=prev,
                    as_of=datetime(2026, 5, 19, tzinfo=UTC),
                )
        return out


async def _mk_user(
    db: AsyncSession, email: str, tier: UserTier = UserTier.PRO
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
    return {
        "Authorization": f"Bearer {create_access_token(user.id, user.email)}"
    }


def _client_app(client: AsyncClient):
    return client._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def _mock_fetcher(client: AsyncClient):
    app = _client_app(client)
    app.dependency_overrides[get_live_price_fetcher] = lambda: _MockFetcher()
    yield
    app.dependency_overrides.pop(get_live_price_fetcher, None)


@pytest.mark.asyncio
async def test_post_alert_creates(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api1@x.tw")
    r = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "NVDA drop",
            "rule_type": "POSITION_PRICE_DROP",
            "threshold_value": "10",
            "threshold_type": "PCT",
            "symbol": "NVDA",
            "market": "US_NASDAQ",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "NVDA drop"
    # Decimal(24,8) round-trips with full precision — accept both
    # "10" and "10.00000000" so the schema's str(Decimal) behaviour
    # remains a free choice.
    from decimal import Decimal as _D

    assert _D(body["threshold_value"]) == _D("10")
    assert body["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_post_alert_400_on_invalid_combo(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api2@x.tw")
    r = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "x",
            "rule_type": "POSITION_PRICE_DROP",
            "threshold_value": "10",
            "threshold_type": "PCT",
            # symbol/market omitted on a POSITION_ rule
        },
        headers=_auth(user),
    )
    assert r.status_code == 400
    assert "invalid_alert_rule" in r.json()["message"]


@pytest.mark.asyncio
async def test_get_alerts_lists_user_rules_only(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    u1 = await _mk_user(db_session, "api3a@x.tw")
    u2 = await _mk_user(db_session, "api3b@x.tw")
    await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "u1 rule",
            "rule_type": "PORTFOLIO_VALUE_ABOVE",
            "threshold_value": "100",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(u1),
    )
    await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "u2 rule",
            "rule_type": "PORTFOLIO_VALUE_ABOVE",
            "threshold_value": "200",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(u2),
    )

    r = await client.get("/api/v1/holdings/alerts", headers=_auth(u1))
    assert r.status_code == 200
    names = [row["name"] for row in r.json()]
    assert names == ["u1 rule"]


@pytest.mark.asyncio
async def test_patch_alert_updates_name_and_status(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api4@x.tw")
    create = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "orig",
            "rule_type": "PORTFOLIO_VALUE_ABOVE",
            "threshold_value": "100",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(user),
    )
    rule_id = create.json()["id"]
    r = await client.patch(
        f"/api/v1/holdings/alerts/{rule_id}",
        json={"name": "renamed", "status": "PAUSED"},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "renamed"
    assert body["status"] == "PAUSED"


@pytest.mark.asyncio
async def test_patch_alert_404_for_other_user(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    u1 = await _mk_user(db_session, "api5a@x.tw")
    u2 = await _mk_user(db_session, "api5b@x.tw")
    create = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "u1",
            "rule_type": "PORTFOLIO_VALUE_ABOVE",
            "threshold_value": "100",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(u1),
    )
    rule_id = create.json()["id"]
    r = await client.patch(
        f"/api/v1/holdings/alerts/{rule_id}",
        json={"name": "hijack"},
        headers=_auth(u2),
    )
    assert r.status_code == 404
    assert r.json()["message"] == "alert_rule_not_found"


@pytest.mark.asyncio
async def test_delete_alert(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api6@x.tw")
    create = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "todel",
            "rule_type": "PORTFOLIO_VALUE_ABOVE",
            "threshold_value": "100",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(user),
    )
    rule_id = create.json()["id"]
    r = await client.delete(
        f"/api/v1/holdings/alerts/{rule_id}", headers=_auth(user)
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # Subsequent GET should not list it.
    r2 = await client.get("/api/v1/holdings/alerts", headers=_auth(user))
    assert r2.json() == []


@pytest.mark.asyncio
async def test_evaluate_now_returns_result(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api7@x.tw")
    create = await client.post(
        "/api/v1/holdings/alerts",
        json={
            "name": "eval",
            "rule_type": "PORTFOLIO_VALUE_BELOW",
            "threshold_value": "1000000000",
            "threshold_type": "ABSOLUTE",
        },
        headers=_auth(user),
    )
    rule_id = create.json()["id"]
    r = await client.post(
        f"/api/v1/holdings/alerts/{rule_id}/evaluate", headers=_auth(user)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Empty portfolio → value 0 <= 1e9 → triggered.
    assert body["triggered"] is True


@pytest.mark.asyncio
async def test_evaluate_unknown_rule_returns_404(
    client: AsyncClient, db_session: AsyncSession, _mock_fetcher: None
) -> None:
    user = await _mk_user(db_session, "api8@x.tw")
    r = await client.post(
        "/api/v1/holdings/alerts/99999/evaluate", headers=_auth(user)
    )
    assert r.status_code == 404
    assert r.json()["message"] == "alert_rule_not_found"
