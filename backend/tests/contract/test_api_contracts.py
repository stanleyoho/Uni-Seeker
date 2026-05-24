"""
API contract tests — verify response shapes match frontend expectations.
Run with: pytest tests/contract/ -v

Requirements:
    pip install httpx  (if not already installed)
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_strategies_response_shape(client):
    res = await client.get("/api/v1/strategies/")
    assert res.status_code == 200
    data = res.json()
    assert "strategies" in data
    for s in data["strategies"]:
        assert "name" in s
        assert "description" in s
        assert "params" in s


@pytest.mark.asyncio
async def test_health_response_shape(client):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "services" in data
