from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.config import Settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.app_name == "Uni-Seeker"
    assert "postgresql+asyncpg" in s.database_url
    assert s.debug is False


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNI_DEBUG", "true")
    monkeypatch.setenv("UNI_APP_NAME", "Test")
    s = Settings()
    assert s.debug is True
    assert s.app_name == "Test"
