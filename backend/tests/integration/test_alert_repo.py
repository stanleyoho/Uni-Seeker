"""Integration tests for AlertRuleRepo."""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserTier
from app.models.user import User
from app.repositories.alerts.alert_repo import AlertRuleRepo


async def _mk_user(db: AsyncSession, email: str) -> User:
    u = User(
        email=email,
        hashed_password="x" * 60,
        username=email.split("@")[0],
    )
    u.tier = UserTier.PRO
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_and_get(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "alert1@test.com")
    repo = AlertRuleRepo(db_session)
    rule = await repo.create(
        user_id=user.id,
        name="NVDA stop loss",
        rule_type="POSITION_PRICE_DROP",
        threshold_value=Decimal("10"),
        threshold_type="PCT",
        symbol="NVDA",
        market="US_NASDAQ",
    )
    await db_session.commit()

    fetched = await repo.get(rule.id, user_id=user.id)
    assert fetched is not None
    assert fetched.name == "NVDA stop loss"
    assert fetched.threshold_value == Decimal("10")


@pytest.mark.asyncio
async def test_get_isolates_users(db_session: AsyncSession) -> None:
    u1 = await _mk_user(db_session, "iso1@test.com")
    u2 = await _mk_user(db_session, "iso2@test.com")
    repo = AlertRuleRepo(db_session)
    rule = await repo.create(
        user_id=u1.id,
        name="rule",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("100"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()

    # Other user must not see it.
    assert await repo.get(rule.id, user_id=u2.id) is None


@pytest.mark.asyncio
async def test_list_by_user_and_count(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "list1@test.com")
    repo = AlertRuleRepo(db_session)
    for i in range(3):
        await repo.create(
            user_id=user.id,
            name=f"rule {i}",
            rule_type="PORTFOLIO_VALUE_ABOVE",
            threshold_value=Decimal("100"),
            threshold_type="ABSOLUTE",
        )
    await db_session.commit()
    rules = await repo.list_by_user(user.id)
    assert len(rules) == 3
    assert await repo.count_by_user(user.id) == 3


@pytest.mark.asyncio
async def test_list_active_filters(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "active1@test.com")
    repo = AlertRuleRepo(db_session)
    active = await repo.create(
        user_id=user.id,
        name="active",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("100"),
        threshold_type="ABSOLUTE",
    )
    paused = await repo.create(
        user_id=user.id,
        name="paused",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("200"),
        threshold_type="ABSOLUTE",
        status="PAUSED",
    )
    await db_session.commit()
    actives = await repo.list_active_by_user(user.id)
    ids = {r.id for r in actives}
    assert active.id in ids
    assert paused.id not in ids


@pytest.mark.asyncio
async def test_update_fields(db_session: AsyncSession) -> None:
    user = await _mk_user(db_session, "upd1@test.com")
    repo = AlertRuleRepo(db_session)
    rule = await repo.create(
        user_id=user.id,
        name="orig",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("100"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    updated = await repo.update(
        rule.id, user_id=user.id, name="renamed", status="PAUSED"
    )
    assert updated is not None
    assert updated.name == "renamed"
    assert updated.status == "PAUSED"


@pytest.mark.asyncio
async def test_delete_returns_false_on_other_user(
    db_session: AsyncSession,
) -> None:
    u1 = await _mk_user(db_session, "del1@test.com")
    u2 = await _mk_user(db_session, "del2@test.com")
    repo = AlertRuleRepo(db_session)
    rule = await repo.create(
        user_id=u1.id,
        name="r",
        rule_type="PORTFOLIO_VALUE_ABOVE",
        threshold_value=Decimal("100"),
        threshold_type="ABSOLUTE",
    )
    await db_session.commit()
    assert await repo.delete(rule.id, user_id=u2.id) is False
    assert await repo.delete(rule.id, user_id=u1.id) is True
