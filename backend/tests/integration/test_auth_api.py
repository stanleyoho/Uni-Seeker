import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.main import create_app
from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def app_with_auth():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    app = create_app()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_register_and_login(app_with_auth) -> None:
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register
        resp = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com", "password": "secret123", "username": "tester",
        })
        assert resp.status_code == 201
        token = resp.json()["access_token"]

        # Get me
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "test@example.com"
        assert resp.json()["tier"] == "free"

        # Login
        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@example.com", "password": "secret123",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()


async def test_duplicate_email(app_with_auth) -> None:
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "password": "pass", "username": "user1",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "email": "dup@test.com", "password": "pass2", "username": "user2",
        })
        assert resp.status_code == 400


async def test_wrong_password(app_with_auth) -> None:
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json={
            "email": "user@test.com", "password": "correct", "username": "u",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "user@test.com", "password": "wrong",
        })
        assert resp.status_code == 401


async def test_no_token_me(app_with_auth) -> None:
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)
