"""Plan 8 T5 — Prometheus metrics tests (Uni-Seeker)."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_metrics_module_exports_expected_counters():
    """Public metric symbols are exposed at module level."""
    from app.obs import metrics

    assert hasattr(metrics, "TIER_UPGRADE_TOTAL")
    assert hasattr(metrics, "TIER_DOWNGRADE_TOTAL")
    assert hasattr(metrics, "AUDIT_EVENT_TOTAL")
    assert hasattr(metrics, "KYC_COMPLETED_TOTAL")
    assert hasattr(metrics, "DEVICE_BLOCKED_TOTAL")
    assert hasattr(metrics, "TIER_GUARD_BLOCK_TOTAL")
    assert hasattr(metrics, "STRIPE_WEBHOOK_TOTAL")
    assert hasattr(metrics, "SUBSCRIPTION_ACTIVE")


def test_tier_upgrade_counter_increments():
    from app.obs.metrics import TIER_UPGRADE_TOTAL

    before = TIER_UPGRADE_TOTAL.labels(
        from_tier="free", to_tier="pro", source="webhook"
    )._value.get()
    TIER_UPGRADE_TOTAL.labels(from_tier="free", to_tier="pro", source="webhook").inc()
    after = TIER_UPGRADE_TOTAL.labels(
        from_tier="free", to_tier="pro", source="webhook"
    )._value.get()
    assert after == before + 1


async def test_audit_event_counter_increments_on_log_audit_event(db_session):
    """log_audit_event() must bump AUDIT_EVENT_TOTAL with the right labels."""
    from app.obs.metrics import AUDIT_EVENT_TOTAL
    from app.services.audit import log_audit_event

    before = AUDIT_EVENT_TOTAL.labels(action="kyc_completed", actor_type="user")._value.get()
    await log_audit_event(db_session, action="kyc_completed", user_id=1)
    after = AUDIT_EVENT_TOTAL.labels(action="kyc_completed", actor_type="user")._value.get()
    assert after == before + 1


def test_subscription_active_gauge_is_gauge():
    from prometheus_client import Gauge

    from app.obs.metrics import SUBSCRIPTION_ACTIVE

    assert isinstance(SUBSCRIPTION_ACTIVE, Gauge)


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text(monkeypatch):
    """A FastAPI app with Instrumentator exposes /metrics with our counters."""
    monkeypatch.setenv("ENV", "test")
    from prometheus_fastapi_instrumentator import Instrumentator

    from app.obs.metrics import TIER_UPGRADE_TOTAL

    # Bump once so the counter is materialized in the registry text output.
    TIER_UPGRADE_TOTAL.labels(from_tier="free", to_tier="pro", source="webhook").inc(0)

    app = FastAPI()
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    body = r.text
    assert "uni_tier_upgrade_total" in body  # custom counter exposed
