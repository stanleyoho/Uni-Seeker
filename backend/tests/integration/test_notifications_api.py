import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.main import create_app
from app.models.base import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def app_with_notifications():
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


async def test_create_and_list_rules(app_with_notifications) -> None:
    transport = ASGITransport(app=app_with_notifications)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create
        resp = await client.post("/api/v1/notifications/rules", json={
            "name": "RSI Alert",
            "rule_type": "indicator_alert",
            "symbol": "2330.TW",
            "conditions": {"indicator": "RSI", "op": "<", "value": 30},
        })
        assert resp.status_code == 201
        rule_id = resp.json()["id"]

        # List
        resp = await client.get("/api/v1/notifications/rules")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["rules"][0]["name"] == "RSI Alert"


async def test_delete_rule(app_with_notifications) -> None:
    transport = ASGITransport(app=app_with_notifications)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create
        resp = await client.post("/api/v1/notifications/rules", json={
            "name": "Test", "rule_type": "price_alert", "symbol": "AAPL",
        })
        rule_id = resp.json()["id"]

        # Delete (soft)
        resp = await client.delete(f"/api/v1/notifications/rules/{rule_id}")
        assert resp.status_code == 204

        # Verify not in list
        resp = await client.get("/api/v1/notifications/rules")
        assert resp.json()["total"] == 0


async def test_delete_nonexistent_rule(app_with_notifications) -> None:
    transport = ASGITransport(app=app_with_notifications)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/api/v1/notifications/rules/999")
        assert resp.status_code == 404
