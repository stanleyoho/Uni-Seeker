"""Plan 8 T1 — structlog config tests (Uni-Seeker)."""

import io
import json
from contextlib import redirect_stdout

import pytest


def test_logging_emits_iso_timestamp(monkeypatch):
    """ISO8601 UTC timestamp must be in every log record."""
    monkeypatch.setenv("ENV", "prod")  # JSON renderer
    from app.obs.logging import configure_logging, get_logger

    configure_logging(service="uni-seeker-backend")
    log = get_logger("test_component")
    buf = io.StringIO()
    with redirect_stdout(buf):
        log.info("hello")
    line = buf.getvalue().strip()
    payload = json.loads(line)
    assert "timestamp" in payload
    # ISO8601 UTC ends with 'Z' or '+00:00'
    ts = payload["timestamp"]
    assert ts.endswith("Z") or ts.endswith("+00:00")


def test_logging_emits_service_field(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    from app.obs.logging import configure_logging, get_logger

    configure_logging(service="uni-seeker-backend")
    log = get_logger("c")
    buf = io.StringIO()
    with redirect_stdout(buf):
        log.info("e")
    payload = json.loads(buf.getvalue().strip())
    assert payload["service"] == "uni-seeker-backend"


def test_logging_dev_uses_console_renderer(monkeypatch):
    """dev / test ENV must produce non-JSON output (console renderer)."""
    monkeypatch.setenv("ENV", "dev")
    from app.obs.logging import configure_logging, get_logger

    configure_logging(service="uni-seeker-backend")
    log = get_logger("c")
    buf = io.StringIO()
    with redirect_stdout(buf):
        log.info("hello-dev")
    line = buf.getvalue().strip()
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)  # must not be valid JSON
    assert "hello-dev" in line


def test_logging_prod_outputs_required_fields(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    from app.obs.logging import configure_logging, get_logger

    configure_logging(service="uni-seeker-backend", version="1.0.0+abc")
    log = get_logger("billing_webhook")
    buf = io.StringIO()
    with redirect_stdout(buf):
        log.info("audit_event", action="tier_upgrade", user_id=42)
    payload = json.loads(buf.getvalue().strip())
    # Per Plan 8 T1 common fields:
    assert payload["service"] == "uni-seeker-backend"
    assert payload["environment"] == "prod"
    assert payload["version"] == "1.0.0+abc"
    assert payload["event"] == "audit_event"
    assert payload["action"] == "tier_upgrade"
    assert payload["user_id"] == 42
    assert payload["level"] == "info"
