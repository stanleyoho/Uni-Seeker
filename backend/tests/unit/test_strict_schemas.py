"""Schema strictness regression tests.

Background
==========
The November 2026 audit found PR #103 had silently dropped a typo'd
field (``strategies_keys`` instead of ``strategy_keys``) on the signal
scanner POST body. Pydantic's default ``extra="ignore"`` swallowed the
key, the request validated, and the scan ran with no strategies. Bug
was invisible until a manual QA noticed all results were empty.

These tests guard the ``StrictModel`` contract — every request body
schema MUST reject unknown fields with a 422 ``ValidationError``, so
the next typo-vs-stale-field-name divergence fails loud.

We intentionally test a representative sample (one per audit-cited
module) rather than every schema — full conversion is enforced by code
review, not by enumeration. The point of this file is that the *base
class actually does the thing* and that the PR #103 scenario can never
recur for the cited endpoints.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.holdings.account import AccountCreateRequest
from app.schemas.journal import AccountCreate as JournalAccountCreate
from app.schemas.scanner import SignalScanRequest
from app.schemas.watchlist import WatchlistAddRequest


class TestSignalScanRequestStrict:
    """The PR #103 regression — typo'd field must fail-loud."""

    def test_valid_payload_accepted(self) -> None:
        # Canonical field name — this is the shape PR #103 *should* have sent.
        req = SignalScanRequest(strategy_keys=["x"])
        assert req.strategy_keys == ["x"]

    def test_typo_field_rejected(self) -> None:
        """``strategies_keys`` (typo) must raise — was silently dropped pre-fix."""
        with pytest.raises(ValidationError) as exc_info:
            # The original PR #103 bug payload.
            # mypy: strategies_keys is not a real field, that's the point.
            SignalScanRequest(strategies_keys=["x"])  # type: ignore[call-arg]
        # The error should mention the offending field name so the client
        # operator can fix their payload without trawling logs.
        msg = str(exc_info.value)
        assert "strategies_keys" in msg
        assert "extra" in msg.lower() or "forbid" in msg.lower()

    def test_unknown_top_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SignalScanRequest(foo_bar=123)  # type: ignore[call-arg]


class TestOtherRequestSchemasStrict:
    """Spot-check that StrictModel adoption holds across other modules.

    One representative schema per audit-cited area. Failure here means
    someone removed the StrictModel inheritance from a request body.
    """

    def test_login_request_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.co", password="x", remember_me=True)  # type: ignore[call-arg]

    def test_register_request_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.co",
                password="Passw0rd!",
                username="alice",
                role="admin",  # type: ignore[call-arg]
            )

    def test_watchlist_add_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            WatchlistAddRequest(symbol="2330", note="hi")  # type: ignore[call-arg]

    def test_holdings_account_create_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            AccountCreateRequest(
                name="My TW",
                market="TW_TWSE",  # type: ignore[arg-type]
                unexpected="boom",  # type: ignore[call-arg]
            )

    def test_journal_account_create_rejects_unknown(self) -> None:
        with pytest.raises(ValidationError):
            JournalAccountCreate(
                name="Acc",
                market="TW",
                currency="TWD",
                bogus_extra=1,  # type: ignore[call-arg]
            )
