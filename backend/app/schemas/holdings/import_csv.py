"""CSV import DTOs for /api/v1/holdings/imports/csv.

Phase 4 extensibility hook (spec §11). Module is named `import_csv.py`
(not `import.py`) because `import` is a Python reserved word and would
break `from app.schemas.holdings.import import …` re-exports.

Wire contract:

    ImportResultRow — one row of the dry-run / commit report. All
    Decimal-ish values are kept as strings so the frontend can render
    them verbatim without re-parsing.

    ImportResult — top-level body: rows parsed, successes, failures,
    full error list, and a `dry_run` echo so the client knows whether
    DB writes actually happened.
"""
from __future__ import annotations

from pydantic import BaseModel


class ImportResultRow(BaseModel):
    """One CSV row's import status.

    ``row_index`` is 1-based against the original file (header row is
    row 1, the first data row is row 2). When a row fails validation,
    ``error`` is populated with a short identifier; otherwise it is None.

    All numeric fields are echoed as-string so the frontend dry-run
    preview can render the raw CSV value rather than a parsed Decimal.
    """

    row_index: int
    action: str | None = None
    symbol: str | None = None
    quantity: str | None = None
    price: str | None = None
    trade_date: str | None = None
    error: str | None = None


class ImportResult(BaseModel):
    """Result of a CSV import — dry-run preview or committed batch.

    Atomicity: when ``dry_run`` is False, the only valid outcomes are
    ``failed_rows == 0 and successful_rows == parsed_rows`` (full commit)
    or ``successful_rows == 0`` (full rollback). Mixed states are not
    representable: the service rolls back the whole batch on any failure.
    """

    parsed_rows: int
    successful_rows: int
    failed_rows: int
    errors: list[ImportResultRow]
    dry_run: bool


__all__ = ["ImportResult", "ImportResultRow"]
