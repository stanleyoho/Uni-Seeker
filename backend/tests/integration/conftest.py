"""Shared fixtures for integration tests."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token
from app.models.enums import UserTier
from app.models.user import User


@pytest.fixture
async def pro_user_token(db_session: AsyncSession) -> dict[str, str]:
    """Create a PRO-tier user in the shared db_session and return Authorization header dict.

    Used by tests that depend on the standard `client` / `db_session` fixtures from
    the top-level conftest. For tests with their own DB engine (e.g. test_backtest_api),
    seed a user inside the local fixture instead.
    """
    user = User(
        email="pro_test@example.com",
        hashed_password="x" * 60,
        username="pro_test",
    )
    user.tier = UserTier.PRO
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}
