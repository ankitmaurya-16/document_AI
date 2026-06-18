"""Uniform JSON error responses and a small exception hierarchy.

Keeps route handlers free of try/except boilerplate: raise a semantic error
(``ValidationError``, ``AuthError``, ...) and the registered handler renders it.
"""
from __future__ import annotations

from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError as PydanticValidationError
from werkzeug.exceptions import HTTPException

from logging_config import get_logger

log = get_logger("errors")


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"


class AuthError(AppError):
    status_code = 401
    code = "auth_error"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class PaymentRequiredError(AppError):
    status_code = 402
    code = "credits_exhausted"


def _json_error(status: int, code: str, message: str, *, details: Any = None):
    # Shape kept backwards-compatible with the existing frontend:
    #   `error` is the human message (string), `code`/`details` are the v1 additions.
    body: dict[str, Any] = {"error": message, "code": code}
    if details is not None:
        body["details"] = details
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(err: AppError):
        log.warning("app_error", code=err.code, message=err.message, details=err.details)
        return _json_error(err.status_code, err.code, err.message, details=err.details)

    @app.errorhandler(PydanticValidationError)
    def _pydantic_error(err: PydanticValidationError):
        simplified = [
            {"loc": ".".join(str(p) for p in e.get("loc", [])), "msg": e.get("msg")}
            for e in err.errors()
        ]
        log.info("validation_error", errors=simplified)
        return _json_error(400, "validation_error", "Request validation failed", details=simplified)

    @app.errorhandler(HTTPException)
    def _http_exc(err: HTTPException):
        return _json_error(err.code or 500, f"http_{err.code}", err.description or err.name)

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        log.exception("unhandled_exception", error=str(err))
        # In prod, never leak the raw message.
        from settings import get_settings

        message = "Internal server error" if get_settings().is_prod else str(err)
        return _json_error(500, "internal_error", message)
