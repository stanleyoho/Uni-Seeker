"""Institutional 13F tracking — pure domain layer.

Spec: docs/superpowers/plans/2026-05-22-institutional-13f-tracking-design.md.

This package contains the Phase 1 domain modules for the 13F holdings
tracker. Each submodule is intentionally narrow:

- ``edgar_client`` — async httpx wrapper around SEC EDGAR endpoints
  (the ONE permitted I/O surface in this layer, per spec §5 R-domain).
- ``parser`` — pure infotable.xml → dataclass parsing. No network, no DB.
- ``diff`` — pure quarter-over-quarter holdings classification.

Anti-coupling invariants (spec §11.2):
- NO imports from ``app.db.*`` / ``sqlalchemy`` / ``fastapi``
- NO imports from ``smart_money.*``
- Service layer depends on these modules, not vice versa.
"""

from __future__ import annotations

from app.modules.institutional.diff import (
    ChangeType,
    HoldingChange,
    compute_diff,
)
from app.modules.institutional.edgar_client import (
    EdgarClient,
    EdgarRateLimiter,
    EdgarTransientError,
    FilerMetadata,
    FilingMetadata,
)
from app.modules.institutional.parser import (
    FilingSummary,
    ParsedHolding,
    ParseError,
    is_valid_cusip,
    parse_infotable_xml,
    summarize_filing,
)

__all__ = [
    # edgar_client
    "EdgarClient",
    "EdgarRateLimiter",
    "EdgarTransientError",
    "FilerMetadata",
    "FilingMetadata",
    # parser
    "FilingSummary",
    "ParsedHolding",
    "ParseError",
    "is_valid_cusip",
    "parse_infotable_xml",
    "summarize_filing",
    # diff
    "ChangeType",
    "HoldingChange",
    "compute_diff",
]
