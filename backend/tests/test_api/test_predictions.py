"""Integration tests for /api/v1/predictions endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_post_save_prediction_returns_201() -> None:
    """POST /api/v1/predictions/save creates a prediction and returns the id."""
    from app.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/predictions/save",
            json={
                "domain": "stocks",
                "entity_id": "2330.TW",
                "model_version": "stocks_v3",
                "prediction_value": 0.65,
                "confidence": 0.80,
                "shap_values": {"pe_ratio": 0.22, "rsi": -0.10},
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert "prediction_id" in data
    assert isinstance(data["prediction_id"], int)


@pytest.mark.anyio
async def test_post_resolve_prediction_returns_200() -> None:
    """POST /api/v1/predictions/resolve/{id} resolves a prediction."""
    from app.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        save_resp = await client.post(
            "/api/v1/predictions/save",
            json={
                "domain": "stocks",
                "entity_id": "2454.TW",
                "model_version": "stocks_v3",
                "prediction_value": 0.60,
                "confidence": 0.75,
            },
        )
        assert save_resp.status_code == 201
        pid = save_resp.json()["prediction_id"]

        resolve_resp = await client.post(
            f"/api/v1/predictions/resolve/{pid}",
            json={"actual_value": 0.025},
        )
    assert resolve_resp.status_code == 200
    data = resolve_resp.json()
    assert data["prediction_id"] == pid
    assert data["is_resolved"] is True


@pytest.mark.anyio
async def test_post_resolve_not_found_returns_404() -> None:
    """Resolving non-existent prediction returns 404."""
    from app.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/predictions/resolve/99999999",
            json={"actual_value": 0.01},
        )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_post_resolve_already_resolved_returns_409() -> None:
    """Re-resolving a prediction returns 409 Conflict."""
    from app.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        save_resp = await client.post(
            "/api/v1/predictions/save",
            json={
                "domain": "stocks",
                "entity_id": "3008.TW",
                "model_version": "stocks_v3",
                "prediction_value": 0.70,
                "confidence": 0.85,
            },
        )
        pid = save_resp.json()["prediction_id"]
        first = await client.post(
            f"/api/v1/predictions/resolve/{pid}",
            json={"actual_value": 0.01},
        )
        assert first.status_code == 200
        conflict_resp = await client.post(
            f"/api/v1/predictions/resolve/{pid}",
            json={"actual_value": -0.01},
        )
    assert conflict_resp.status_code == 409


@pytest.mark.anyio
async def test_get_performance_window_returns_stats() -> None:
    """GET /api/v1/predictions/performance returns accuracy stats."""
    from app.main import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/predictions/performance",
            params={"domain": "stocks", "days": 7},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "accuracy" in data
