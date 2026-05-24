import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger()


# --- Standard error response helper ---


def _error_response(
    status_code: int, error: str, message: str, detail: str | None = None
) -> JSONResponse:
    """Build a standardised JSON error response."""
    body: dict[str, str] = {"error": error, "message": message}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body)


# --- Application error hierarchy ---


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "APP_ERROR",
        detail: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} '{identifier}' not found",
            status_code=404,
            error_code="NOT_FOUND",
        )


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=422, error_code="VALIDATION_ERROR")


class ExternalServiceError(AppError):
    def __init__(self, service: str, message: str) -> None:
        super().__init__(
            message=f"External service error ({service}): {message}",
            status_code=502,
            error_code="EXTERNAL_SERVICE_ERROR",
        )


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            error_code=exc.error_code,
            status_code=exc.status_code,
            message=exc.message,
            path=request.url.path,
        )
        return _error_response(
            status_code=exc.status_code,
            error=exc.error_code,
            message=exc.message,
            detail=exc.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "validation_error",
            errors=exc.errors(),
            path=request.url.path,
        )
        return _error_response(
            status_code=422,
            error="VALIDATION_ERROR",
            message="Request validation failed",
            detail=str(exc.errors()),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
        )
        return _error_response(
            status_code=exc.status_code,
            error="HTTP_ERROR",
            message=str(exc.detail) if exc.detail else "HTTP error",
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_error",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
            exc_info=True,
        )
        return _error_response(
            status_code=500,
            error="INTERNAL_ERROR",
            message="Internal server error",
            detail="An unexpected error occurred",
        )
