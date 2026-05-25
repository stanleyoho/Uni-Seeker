"""Quarter-over-quarter 13F holdings diff engine — pure module.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md
§7.2 (diff contract), §11.R6 (amendment / multi-row handling).

**Aggregation decision (per spec §7.2):**

The XML natural key is ``(cusip, put_call)`` — same CUSIP can appear
multiple times under different ``putCall`` values. For Phase 1 we
**aggregate by ``cusip``** (summing shares/value across put_call
variants) when computing change classification. Rationale:

- The user-facing "did Leopold buy more NVDA this quarter?" question
  treats common stock + CALL options on NVDA as the same conviction.
- Reporting ``HoldingChange`` per-cusip keeps the diff list tractable
  for big filers; per-row diff explodes line counts.
- We **preserve** the put_call breakdown inside the row, but the
  natural key for the diff is bare CUSIP.

If callers later want per-put_call diffs, that's a separate function;
this module exports the aggregated view.

Pure-function rules (anti-coupling §11.2):
- No DB, no network, no FastAPI.
- ``ParsedHolding`` is the only inbound type; ``HoldingChange`` is the
  only outbound type. Service layer translates to ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.modules.institutional.parser import ParsedHolding

__all__ = [
    "ChangeType",
    "HoldingChange",
    "compute_diff",
]

_ZERO = Decimal("0")


class ChangeType(StrEnum):
    """5-way classification per spec §7.2.

    Inherits from ``str`` so it serializes cleanly via FastAPI/Pydantic
    in the API layer, even though this module itself doesn't import them.
    """

    NEW = "NEW"
    EXITED = "EXITED"
    INCREASED = "INCREASED"
    DECREASED = "DECREASED"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class HoldingChange:
    """One row of the diff report (aggregated by CUSIP).

    For NEW rows, ``prev_*`` fields are None; for EXITED rows, ``curr_*``
    fields are None. ``delta_*`` are always populated (negative for
    DECREASED / EXITED). ``delta_pct`` is None when one side is missing
    (no meaningful % change for NEW or EXITED positions).
    """

    cusip: str
    name_of_issuer: str
    change_type: ChangeType
    prev_shares: Decimal | None
    curr_shares: Decimal | None
    delta_shares: Decimal  # curr - prev
    delta_pct: Decimal | None  # (curr - prev) / prev when defined
    prev_value_usd: Decimal | None
    curr_value_usd: Decimal | None
    delta_value_usd: Decimal


def compute_diff(
    prev_holdings: list[ParsedHolding],
    curr_holdings: list[ParsedHolding],
) -> list[HoldingChange]:
    """Diff two quarterly snapshots, aggregating by CUSIP.

    Aggregation:
    - shares = Σ across all put_call variants (treating ``None`` shares
      from PRN rows as 0 for the change calculation).
    - value_usd = Σ across all put_call variants (long + options notional).
    - name_of_issuer = the first non-empty name encountered in *curr*,
      falling back to *prev*. SEC name strings are free-text and may
      vary slightly between filings; we don't try to canonicalize.

    Output order: deterministic — sorted by CUSIP ascending. Stable
    ordering keeps API responses snapshot-testable.

    Returns:
        List of ``HoldingChange`` covering the **union** of CUSIPs in
        either snapshot, including ``UNCHANGED`` rows (callers filter
        as needed). Empty input on either side is fine — yields all-NEW
        or all-EXITED accordingly.
    """
    prev_agg = _aggregate_by_cusip(prev_holdings)
    curr_agg = _aggregate_by_cusip(curr_holdings)

    all_cusips = sorted(set(prev_agg.keys()) | set(curr_agg.keys()))
    out: list[HoldingChange] = []
    for cusip in all_cusips:
        prev = prev_agg.get(cusip)
        curr = curr_agg.get(cusip)
        out.append(_classify(cusip, prev, curr))
    return out


# ───────────────────────── private ─────────────────────────


@dataclass
class _Aggregated:
    """Per-CUSIP rollup used internally by compute_diff."""

    cusip: str
    name_of_issuer: str
    shares: Decimal
    value_usd: Decimal


def _aggregate_by_cusip(holdings: list[ParsedHolding]) -> dict[str, _Aggregated]:
    """Group by CUSIP, summing shares and value across all put_call variants."""
    out: dict[str, _Aggregated] = {}
    for h in holdings:
        existing = out.get(h.cusip)
        # PRN rows have shares=None — they contribute to value_usd only.
        shares_contribution = h.shares if h.shares is not None else _ZERO
        if existing is None:
            out[h.cusip] = _Aggregated(
                cusip=h.cusip,
                name_of_issuer=h.name_of_issuer,
                shares=shares_contribution,
                value_usd=h.value_usd,
            )
        else:
            existing.shares += shares_contribution
            existing.value_usd += h.value_usd
            if not existing.name_of_issuer and h.name_of_issuer:
                existing.name_of_issuer = h.name_of_issuer
    return out


def _classify(
    cusip: str,
    prev: _Aggregated | None,
    curr: _Aggregated | None,
) -> HoldingChange:
    """Build a single ``HoldingChange`` from optional prev/curr aggregates."""
    if prev is None and curr is not None:
        # NEW position
        return HoldingChange(
            cusip=cusip,
            name_of_issuer=curr.name_of_issuer,
            change_type=ChangeType.NEW,
            prev_shares=None,
            curr_shares=curr.shares,
            delta_shares=curr.shares,
            delta_pct=None,
            prev_value_usd=None,
            curr_value_usd=curr.value_usd,
            delta_value_usd=curr.value_usd,
        )
    if prev is not None and curr is None:
        # EXITED — sign convention: delta is negative.
        return HoldingChange(
            cusip=cusip,
            name_of_issuer=prev.name_of_issuer,
            change_type=ChangeType.EXITED,
            prev_shares=prev.shares,
            curr_shares=None,
            delta_shares=-prev.shares,
            delta_pct=None,
            prev_value_usd=prev.value_usd,
            curr_value_usd=None,
            delta_value_usd=-prev.value_usd,
        )
    assert prev is not None  # for type-checker
    assert curr is not None

    delta_shares = curr.shares - prev.shares
    delta_value = curr.value_usd - prev.value_usd

    delta_pct: Decimal | None
    if prev.shares == _ZERO:
        # Was holding via PRN-only rows, now has shares — treat as INCREASED
        # but pct is undefined.
        delta_pct = None
    else:
        delta_pct = (curr.shares - prev.shares) / prev.shares

    if delta_shares > _ZERO:
        change_type = ChangeType.INCREASED
    elif delta_shares < _ZERO:
        change_type = ChangeType.DECREASED
    else:
        change_type = ChangeType.UNCHANGED

    # Prefer curr's name (more recent labeling); fall back to prev.
    name = curr.name_of_issuer or prev.name_of_issuer

    return HoldingChange(
        cusip=cusip,
        name_of_issuer=name,
        change_type=change_type,
        prev_shares=prev.shares,
        curr_shares=curr.shares,
        delta_shares=delta_shares,
        delta_pct=delta_pct,
        prev_value_usd=prev.value_usd,
        curr_value_usd=curr.value_usd,
        delta_value_usd=delta_value,
    )
