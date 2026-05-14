import pytest
from sqlalchemy import func, select

from app.models.enums import UserTier
from app.models.user import User
from app.models.user_device import UserDevice


async def _make_user(db, email="a@x.tw", username="a") -> User:
    u = User(email=email, hashed_password="x" * 60, username=username)
    u.tier = UserTier.FREE
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_can_create_user_device(db_session):
    u = await _make_user(db_session)
    d = UserDevice(user_id=u.id, fingerprint_hash="abc123")
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)
    assert d.id is not None
    assert d.user_id == u.id
    assert d.fingerprint_hash == "abc123"


@pytest.mark.asyncio
async def test_unique_user_fingerprint(db_session):
    u = await _make_user(db_session, "b@x.tw", "b")
    db_session.add(UserDevice(user_id=u.id, fingerprint_hash="fp1"))
    await db_session.commit()
    db_session.add(UserDevice(user_id=u.id, fingerprint_hash="fp1"))
    with pytest.raises(Exception):
        await db_session.commit()


@pytest.mark.asyncio
async def test_cascade_delete_devices_on_user_delete(db_session):
    u = await _make_user(db_session, "c@x.tw", "c")
    db_session.add(UserDevice(user_id=u.id, fingerprint_hash="cfp"))
    await db_session.commit()
    await db_session.delete(u)
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(UserDevice))
    assert count == 0


@pytest.mark.asyncio
async def test_different_users_can_have_same_fingerprint(db_session):
    u1 = await _make_user(db_session, "d1@x.tw", "d1")
    u2 = await _make_user(db_session, "d2@x.tw", "d2")
    db_session.add(UserDevice(user_id=u1.id, fingerprint_hash="shared"))
    db_session.add(UserDevice(user_id=u2.id, fingerprint_hash="shared"))
    await db_session.commit()
    count = await db_session.scalar(select(func.count()).select_from(UserDevice))
    assert count == 2
