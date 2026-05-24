"""trace_id ContextVar + helpers — thin wrapper over observability-core.

Re-exports the public symbols (``TRACE_ID`` / ``new_trace_id`` /
``trace_context``) so existing call sites
(``from app.obs.trace import ...``) keep working unchanged.

Since 2026-05-24 Stage 2 migration the actual implementation lives in
``observability_core.trace``.
"""
from __future__ import annotations

from observability_core.trace import (
    TRACE_ID,
    new_trace_id,
    trace_context,
)

__all__ = ["TRACE_ID", "new_trace_id", "trace_context"]
