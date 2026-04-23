from app.middleware.error_handler import AppError, NotFoundError, ValidationError, ExternalServiceError


def test_app_error() -> None:
    err = AppError("test error", status_code=400)
    assert err.message == "test error"
    assert err.status_code == 400


def test_not_found_error() -> None:
    err = NotFoundError("Stock", "9999.TW")
    assert err.status_code == 404
    assert "9999.TW" in err.message


def test_validation_error() -> None:
    err = ValidationError("invalid input")
    assert err.status_code == 422


def test_external_service_error() -> None:
    err = ExternalServiceError("TWSE", "timeout")
    assert err.status_code == 502
    assert "TWSE" in err.message


def test_app_error_default_detail() -> None:
    err = AppError("msg")
    assert err.detail == "msg"


def test_app_error_custom_detail() -> None:
    err = AppError("msg", detail="custom detail")
    assert err.detail == "custom detail"
