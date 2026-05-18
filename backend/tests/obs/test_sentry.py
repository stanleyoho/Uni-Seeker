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
    # T4: traces_sample_rate is replaced by traces_sampler (mutually exclusive
    # per sentry_sdk). Verify the sampler + before_send callables are wired.
    assert "traces_sample_rate" not in kwargs
    assert callable(kwargs["traces_sampler"])
    assert callable(kwargs["before_send"])
    # baseline propagates: non-special path → 0.25
    assert kwargs["traces_sampler"]({"transaction_context": {"name": "/x"}}) == 0.25
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


# ── before_send filter tests ─────────────────────────────────────────────────


def test_before_send_drops_stripe_4xx():
    """Stripe 4xx errors are user-config issues, not server bugs → drop."""
    from app.obs._sentry_filters import build_before_send
    bs = build_before_send()
    # Fake hint with stripe-like exception
    class FakeStripeError(Exception):
        http_status = 400
    err = FakeStripeError("invalid card")
    err.__class__.__name__ = "InvalidRequestError"
    event = {"exception": {"values": [{"type": "InvalidRequestError"}]}}
    hint = {"exc_info": (type(err), err, None)}
    assert bs(event, hint) is None


def test_before_send_keeps_stripe_5xx():
    from app.obs._sentry_filters import build_before_send
    bs = build_before_send()
    class FakeAPIError(Exception):
        http_status = 502
    err = FakeAPIError("upstream gone")
    err.__class__.__name__ = "APIConnectionError"
    event = {"exception": {"values": [{"type": "APIConnectionError"}]}}
    hint = {"exc_info": (type(err), err, None)}
    assert bs(event, hint) is event


def test_before_send_drops_expected_drift_alert():
    """ExpectedDriftAlert is a notification channel, not a bug."""
    from app.obs._sentry_filters import build_before_send, ExpectedDriftAlert
    bs = build_before_send()
    err = ExpectedDriftAlert("orange drift on nba")
    event = {"exception": {"values": [{"type": "ExpectedDriftAlert"}]}}
    hint = {"exc_info": (type(err), err, None)}
    assert bs(event, hint) is None


def test_before_send_keeps_unhandled_runtime_error():
    from app.obs._sentry_filters import build_before_send
    bs = build_before_send()
    err = RuntimeError("oops")
    event = {"exception": {"values": [{"type": "RuntimeError"}]}}
    hint = {"exc_info": (type(err), err, None)}
    assert bs(event, hint) is event


def test_traces_sampler_skips_health_and_metrics():
    """0% sample for /health and /metrics; full sample for /billing/webhook;
    otherwise return baseline."""
    from app.obs._sentry_filters import build_traces_sampler
    sampler = build_traces_sampler(baseline=0.1)
    assert sampler({"transaction_context": {"name": "/health"}}) == 0.0
    assert sampler({"transaction_context": {"name": "/metrics"}}) == 0.0
    assert sampler({"transaction_context": {"name": "/ready"}}) == 0.0
    assert sampler({"transaction_context": {"name": "/api/v1/billing/webhook"}}) == 1.0
    assert sampler({"transaction_context": {"name": "/api/v1/stocks/2330.TW"}}) == 0.1
    # Missing context → baseline
    assert sampler({}) == 0.1
