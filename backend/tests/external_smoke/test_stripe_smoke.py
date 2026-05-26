"""Stripe signature verification smoke test.

Crucially this does NOT hit Stripe's live API — that would charge or modify
Stanley's account. Instead we exercise the `stripe.Webhook.construct_event`
helper (which is what our `StripeService.handle_webhook` delegates to) with
a payload + signature pair we compute via the documented algorithm.

The point is to detect drift in the `stripe` Python package: if Stripe
changes their signing algorithm or signature header format in a future
major bump, this test fails BEFORE prod webhooks start rejecting events.

Why we don't call `StripeService.handle_webhook` directly: that method does
extra post-parse work (`event.get("id")`, `event["data"]["object"]`) that
assumes a plain dict, but real `construct_event` returns a `StripeObject`.
Unit tests mock around this; here we keep the smoke focused on the actual
crypto contract.
"""

from __future__ import annotations

import hmac
import json
import os
import time
from hashlib import sha256

import pytest
import stripe

# Stripe webhook signature format (from official docs):
#   t=<unix_ts>,v1=HMAC_SHA256(secret, f"{ts}.{payload}")
# Ref: https://stripe.com/docs/webhooks/signatures#verify-manually


def _sign(payload: bytes, secret: str, ts: int) -> str:
    """Construct a Stripe-compatible signature header for `payload`."""
    signed = f"{ts}.{payload.decode()}".encode()
    sig = hmac.new(secret.encode(), signed, sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_stripe_construct_event_accepts_valid_signature() -> None:
    """stripe.Webhook.construct_event must accept a properly-signed payload.

    We skip if `UNI_STRIPE_WEBHOOK_SECRET` is not set in the environment.
    The test value is just a placeholder for the HMAC math; it never
    reaches Stripe's API.
    """
    secret = os.environ.get("UNI_STRIPE_WEBHOOK_SECRET")
    if not secret:
        pytest.skip(
            "UNI_STRIPE_WEBHOOK_SECRET not set — skipping signature smoke. "
            "Set this env var (any non-empty string) to enable the check."
        )

    # Minimal v1 event payload. `"object": "event"` at the top level is
    # required by stripe SDK >=7 — construct_event reads it to discriminate
    # v1 vs v2.core.event payloads. Omitting it raises AttributeError before
    # signature verification even runs.
    payload_dict = {
        "id": "evt_test_smoke_001",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_smoke",
                "metadata": {"user_id": "1", "tier": "basic"},
            }
        },
    }
    payload = json.dumps(payload_dict, separators=(",", ":")).encode()
    signature = _sign(payload, secret, ts=int(time.time()))

    # If Stripe ever changes the signing algorithm or signature header format,
    # this raises stripe.error.SignatureVerificationError.
    event = stripe.Webhook.construct_event(payload, signature, secret)  # type: ignore[no-untyped-call]

    assert event.type == "checkout.session.completed"
    assert event.id == "evt_test_smoke_001"


def test_stripe_construct_event_rejects_bad_signature() -> None:
    """Bad signature must raise SignatureVerificationError — guards against
    a future SDK release silently no-op'ing the check."""
    secret = os.environ.get("UNI_STRIPE_WEBHOOK_SECRET")
    if not secret:
        pytest.skip("UNI_STRIPE_WEBHOOK_SECRET not set — skipping signature smoke.")

    payload = b'{"id":"evt_bad","object":"event","type":"x","data":{"object":{}}}'

    with pytest.raises(stripe.error.SignatureVerificationError):
        stripe.Webhook.construct_event(payload, "t=1,v1=deadbeef", secret)  # type: ignore[no-untyped-call]


def test_stripe_service_imports_cleanly() -> None:
    """Sanity check that our StripeService module still imports — catches
    upstream API removals (e.g. `stripe.error.SignatureVerificationError` going
    away) at the module-import boundary."""
    # Re-import inside the test so any ImportError surfaces here, not at
    # collection time (which would skip alerting on the test itself).
    from app.modules.billing.stripe_service import StripeService  # noqa: F401

    assert hasattr(stripe, "Webhook")
    assert hasattr(stripe.Webhook, "construct_event")
    assert hasattr(stripe.error, "SignatureVerificationError")
