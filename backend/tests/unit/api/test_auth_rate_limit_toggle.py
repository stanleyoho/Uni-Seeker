"""Regression coverage for the auth rate limiter env toggle.

PR introducing this test: the e2e Playwright suite was tripping the prod
``5 attempts / 60s`` limiter and getting 429 on most specs after the first
spec exhausted the window. Backend now reads the cap from settings, and
the e2e docker-compose sets ``UNI_AUTH_RATE_LIMIT_MAX=0`` to disable it.
This test pins both behaviours.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import auth as auth_module


@pytest.fixture
def fresh_store() -> Iterator[None]:
    """Reset the module-level rate-limit dict between tests."""
    auth_module._rate_limit_store.clear()
    yield
    auth_module._rate_limit_store.clear()


def _fake_request(ip: str = "1.2.3.4") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    return req


def test_rate_limit_max_zero_disables_completely(monkeypatch, fresh_store) -> None:
    """With auth_rate_limit_max == 0, the check is a no-op for any number of calls."""
    from app.config import settings

    monkeypatch.setattr(settings, "auth_rate_limit_max", 0)
    req = _fake_request()
    # 1000 calls — way over any plausible limit — must not raise.
    for _ in range(1000):
        auth_module._check_rate_limit(req)
    # Store stays empty because the function returns before recording.
    assert auth_module._rate_limit_store == {}


def test_rate_limit_max_positive_still_trips(monkeypatch, fresh_store) -> None:
    """With auth_rate_limit_max == 3, the 4th call must raise 429."""
    from app.config import settings

    monkeypatch.setattr(settings, "auth_rate_limit_max", 3)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60.0)
    req = _fake_request()
    auth_module._check_rate_limit(req)
    auth_module._check_rate_limit(req)
    auth_module._check_rate_limit(req)
    with pytest.raises(HTTPException) as exc:
        auth_module._check_rate_limit(req)
    assert exc.value.status_code == 429
    assert "60" in exc.value.detail


def test_rate_limit_per_ip_isolated(monkeypatch, fresh_store) -> None:
    """One IP exhausting its budget must not block a different IP."""
    from app.config import settings

    monkeypatch.setattr(settings, "auth_rate_limit_max", 2)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 60.0)
    req_a = _fake_request(ip="10.0.0.1")
    req_b = _fake_request(ip="10.0.0.2")
    auth_module._check_rate_limit(req_a)
    auth_module._check_rate_limit(req_a)
    with pytest.raises(HTTPException):
        auth_module._check_rate_limit(req_a)
    # B is independent.
    auth_module._check_rate_limit(req_b)
    auth_module._check_rate_limit(req_b)
