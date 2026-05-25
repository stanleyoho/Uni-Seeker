"""CSV import endpoint — /api/v1/holdings/imports/* (Phase 4 + Round 10).

Two endpoints:

    POST /imports/csv?broker_key=...&account_id=X&dry_run=...
        Bulk-import trades from a broker CSV. Optional `broker_key`
        selects an adapter explicitly; omit to auto-detect.

    GET /imports/brokers
        List available broker adapters — used by the frontend dropdown.

Wire shape (POST)
~~~~~~~~~~~~~~~~~

We accept the CSV as the **raw request body** with content-type
``text/csv`` (or ``text/plain``). Multipart/form-data is intentionally
avoided so we don't pull in `python-multipart`. Metadata
(``account_id``, ``dry_run``, ``broker_key``) goes on the query string.

File constraints:
    * Content-Type: text/csv or text/plain.
    * Body size: < 1 MiB. Beyond that we 413 — the spec's monthly trade
      cap is 500 and a 1 MiB file is already ~6k rows.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.holdings import _detail as detail
from app.auth import require_auth
from app.schemas.holdings.import_csv import (
    BrokerInfo,
    BrokerListResponse,
    ImportResult,
)
from app.services.portfolio import CsvImportService
from app.services.portfolio.exceptions import (
    PortfolioInsufficientSharesError,
    PortfolioAccountNotFoundError,
    TierLimitExceededError,
)

router = APIRouter(prefix="/imports", tags=["holdings.imports"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[object, Depends(require_auth)]

# 1 MiB — see module docstring for sizing rationale.
_MAX_CSV_BYTES = 1_048_576

# Acceptable raw-body content-types. Broker exports sometimes mis-label
# as text/plain; we keep both. None / empty is also tolerated because
# some HTTP clients omit the header for short text bodies.
_ACCEPTED_CONTENT_TYPES = {
    "text/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/octet-stream",
    "",
}


@router.get(
    "/brokers",
    response_model=BrokerListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_brokers(
    db: DbDep,
    user: UserDep,
) -> BrokerListResponse:
    """List the broker adapters available for CSV import.

    Auth-gated (same dependency stack as every other holdings route)
    so we don't leak the registry to anonymous callers. The list is
    process-stable; the frontend caches it on modal open.
    """
    service = CsvImportService(db, user)  # type: ignore[arg-type]
    return BrokerListResponse(brokers=[BrokerInfo(**b) for b in service.list_brokers()])


@router.post(
    "/csv",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
)
async def import_csv(
    request: Request,
    db: DbDep,
    user: UserDep,
    account_id: int = Query(..., description="Target portfolio account id"),
    dry_run: bool = Query(
        default=False,
        description=(
            "When true, parse + validate only — no DB writes. The "
            "frontend uses this for the preview pass before commit."
        ),
    ),
    broker_key: str | None = Query(
        default=None,
        description=(
            "Optional explicit broker adapter key (e.g. 'interactive_brokers',"
            " 'yuanta'). When omitted, the service auto-detects via "
            "BrokerParser.can_handle() heuristics."
        ),
    ),
) -> ImportResult:
    """Bulk-import trades from a broker CSV.

    Atomic semantics: either every row commits or none. On any row
    failure (validation, FIFO check, tier quota) we let the exception
    bubble up so the dependency-injected session rolls back via FastAPI's
    standard error handling.
    """
    # 1. content-type allowlist on the raw body. We split on `;` so a
    #    `text/csv; charset=utf-8` header still matches.
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=detail.INVALID_CSV_FORMAT,
        )

    # 2. size check via Content-Length header first (cheap), then read
    #    the body. We bail before parsing on either path.
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > _MAX_CSV_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=detail.CSV_TOO_LARGE,
                )
        except ValueError:
            pass

    raw = await request.body()
    if len(raw) > _MAX_CSV_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=detail.CSV_TOO_LARGE,
        )

    # 3. decode UTF-8 (strip optional BOM). Most broker exports in TW
    #    are BIG5 / cp950 today; for Phase 4 we accept utf-8 only and
    #    ask the user to re-export.
    try:
        csv_content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INVALID_CSV_FORMAT,
        ) from exc

    service = CsvImportService(db, user)  # type: ignore[arg-type]
    try:
        result = await service.import_csv(
            account_id=account_id,
            csv_content=csv_content,
            broker_key=broker_key,
            dry_run=dry_run,
        )
    except PortfolioAccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail.ACCOUNT_NOT_FOUND,
        ) from exc
    except TierLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail.limit_exceeded(exc.limit_key),
        ) from exc
    except PortfolioInsufficientSharesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INSUFFICIENT_SHARES,
        ) from exc
    except ValueError as exc:
        # Header missing / malformed / unknown broker_key.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail.INVALID_CSV_FORMAT,
        ) from exc

    # Commit ONLY when dry_run=False AND every row succeeded. Any failure
    # leaves the session dirty-but-uncommitted; FastAPI's session
    # teardown will rollback in the get_db generator's finally block.
    if not dry_run and result.failed_rows == 0:
        await db.commit()
    else:
        await db.rollback()

    return result
