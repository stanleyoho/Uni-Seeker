"""Strict base for request body schemas.

Background — why this exists
============================
The November 2026 audit found only 2/120 Pydantic schemas under
``backend/app/schemas/`` set ``extra="forbid"``. PR #103 lost data because
``SignalScanRequest`` silently dropped a typo'd field (``strategies_keys``
instead of ``strategy_keys``) — Pydantic happily ignored the extra key,
the request validated, and the scan ran with no strategies. The bug was
invisible until a manual QA noticed all results were empty.

Policy
======
Every **request body** schema (the Pydantic class deserialised from a
client POST/PATCH/PUT body) MUST inherit from ``StrictModel``. Response
schemas DO NOT need ``forbid``: the frontend reads them, extras don't
matter on the read side, and locking responses down would force a schema
bump for every additive backend field.

The contract is: typos and stale client field names fail loud (422
``Extra inputs are not permitted``) instead of silently dropping data.

Usage
=====
::

    from app.schemas._base import StrictModel

    class MyRequest(StrictModel):
        symbol: str
        limit: int = 50

Inheriting from ``StrictModel`` instead of ``BaseModel`` is the only
change required — every other Pydantic feature (validators, Field,
model_config overrides) still works. If a schema already declares
``model_config = ConfigDict(...)`` with other settings, merge ``extra``
into that explicit config rather than relying on the inherited one
(Pydantic does not deep-merge ConfigDict across inheritance).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base class for request body schemas.

    Rejects unknown fields with a 422 ``ValidationError`` instead of
    silently dropping them. See module docstring for the policy.
    """

    model_config = ConfigDict(extra="forbid")


__all__ = ["StrictModel"]
