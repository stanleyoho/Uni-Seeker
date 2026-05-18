"""Plan 8 T3 — Sentry SDK init tests."""
from unittest.mock import patch


def test_init_sentry_returns_false_when_dsn_missing(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setenv("ENV", "prod")
    from app.obs.sentry import init_sentry
    ok = init_sentry(service="uni-seeker-backend")
    assert ok is False


def test_init_sentry_returns_true_when_dsn_set(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fakekey@sentry.io/123")
    monkeypatch.setenv("ENV", "prod")
    with patch("app.obs.sentry.sentry_sdk.init") as mock_init, \
         patch("app.obs.sentry.sentry_sdk.set_tag"):
        from app.obs.sentry import init_sentry
        ok = init_sentry(service="uni-seeker-backend")
    assert ok is True
    mock_init.assert_called_once()


def test_init_sentry_passes_environment_release_sample_rate(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fakekey@sentry.io/123")
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("OBS_VERSION", "1.2.3+abc")
    with patch("app.obs.sentry.sentry_sdk.init") as mock_init, \
         patch("app.obs.sentry.sentry_sdk.set_tag"):
        from app.obs.sentry import init_sentry
        init_sentry(service="uni-seeker-backend", traces_sample_rate=0.25)
    kwargs = mock_init.call_args.kwargs
    assert kwargs["environment"] == "staging"
    assert kwargs["release"] == "1.2.3+abc"
    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["send_default_pii"] is False


def test_init_sentry_skipped_in_test_env(monkeypatch):
    """ENV=test must short-circuit even if DSN is set."""
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("SENTRY_DSN", "https://fakekey@sentry.io/123")
    with patch("app.obs.sentry.sentry_sdk.init") as mock_init:
        from app.obs.sentry import init_sentry
        ok = init_sentry(service="uni-seeker-backend")
    assert ok is False
    mock_init.assert_not_called()
