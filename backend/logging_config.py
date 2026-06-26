"""Structured logging with correlation IDs.

Uses structlog to emit JSON logs in prod and human-readable logs in dev.
Every request gets a correlation_id (X-Request-ID header or generated UUID)
that is attached to every log line emitted during that request.
"""
from __future__ import annotations

import logging
import re
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from flask import Flask, g, request

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def _add_correlation_id(logger, method_name, event_dict: dict[str, Any]) -> dict[str, Any]:
    cid = _correlation_id.get()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


# --- PII redaction ----------------------------------------------------------
#
# Logs land in a shared aggregator (and Sentry, when enabled). To keep
# personally identifying data out of long-term storage we run every emitted
# event through a redaction pass: emails, bearer tokens, and 13–19 digit
# card-shaped numbers are replaced with a placeholder. The pass walks str
# fields recursively so kwargs like ``log.info("login", email=...)`` and
# nested dicts (e.g. an ``error`` from a third-party SDK) are both covered.

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_REDACTED = "<redacted>"


def _redact_text(value: str) -> str:
    value = _EMAIL_RE.sub(_REDACTED, value)
    value = _BEARER_RE.sub(f"Bearer {_REDACTED}", value)
    value = _CARD_RE.sub(_REDACTED, value)
    return value


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        redacted = [_redact_value(v) for v in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


def _redact_pii(logger, method_name, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {k: _redact_value(v) for k, v in event_dict.items()}


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    """Configure structlog once at app startup."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Last shared processor — runs after exc_info has been rendered into
        # ``event_dict`` so stack traces are scrubbed too.
        _redact_pii,
    ]

    if json_logs:
        renderer: structlog.typing.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (Flask, werkzeug, openai) through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def install_request_logging(app: Flask) -> None:
    """Attach correlation-id + request/response log hooks to a Flask app."""
    log = get_logger("http")

    @app.before_request
    def _assign_correlation_id() -> None:
        cid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        _correlation_id.set(cid)
        g.correlation_id = cid
        g.log = log.bind(
            method=request.method,
            path=request.path,
            remote=request.remote_addr,
        )
        g.log.info("request.start")

    @app.after_request
    def _log_response(response):
        cid = getattr(g, "correlation_id", None)
        if cid:
            response.headers["X-Request-ID"] = cid
        logger = getattr(g, "log", log)
        logger.info("request.end", status=response.status_code)
        return response

    @app.teardown_request
    def _clear_ctx(_exc):
        _correlation_id.set(None)
