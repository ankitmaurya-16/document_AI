"""Flask application factory.

Wires up:
- Settings validated at startup (fail-fast in prod).
- Structured logging (structlog) with per-request correlation IDs.
- CORS restricted to the explicit allow-list from ``CORS_ALLOWED_ORIGINS``.
- Rate limiter applied per-endpoint from env-driven rules.
- Uniform JSON error responses via ``errors.register_error_handlers``.
- Sentry initialized if ``SENTRY_DSN`` is set.

Routes live in blueprint modules under ``routes/v1/`` and are mounted at
``/api/v1/...``.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

# Load .env before importing settings so fail-fast still reads env vars.
load_dotenv()

# Keep the `from config import ...` imports inside rag/ working.
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BACKEND_DIR, "rag"))

from errors import register_error_handlers  # noqa: E402
from extensions import limiter  # noqa: E402
from logging_config import configure_logging, get_logger, install_request_logging  # noqa: E402
from metrics import init_metrics  # noqa: E402
from middleware.security import install_security_headers  # noqa: E402
from routes.v1 import register_v1  # noqa: E402
from sentry_setup import init_sentry  # noqa: E402
from settings import get_settings  # noqa: E402
from telemetry import init_tracing, instrument_flask  # noqa: E402


def create_app() -> Flask:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
    init_sentry(settings)
    # Tracing must be initialized BEFORE Flask is constructed so the
    # auto-instrumentation can patch wsgi/app on creation.
    init_tracing(service_name="docai-backend")

    log = get_logger("app")
    log.info("app.boot", env=settings.app_env, debug=settings.debug)

    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=(settings.max_upload_mb + 1) * 1024 * 1024,
        JSON_SORT_KEYS=False,
        PROPAGATE_EXCEPTIONS=True,
    )

    CORS(
        app,
        resources={r"/api/*": {"origins": list(settings.cors_allowed_origins)}},
        supports_credentials=True,
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )

    install_request_logging(app)
    install_security_headers(app)
    limiter.init_app(app)
    limiter.default_limits = [settings.rate_limit_default]

    # Observability — both no-op cleanly when their packages or env
    # vars aren't present, so tests / minimal dev setups stay light.
    instrument_flask(app)
    init_metrics(app)

    register_v1(app)

    @app.errorhandler(413)
    def _too_large(_):
        return jsonify({
            "error": f"File too large. Maximum size is {settings.max_upload_mb}MB",
            "code": "payload_too_large",
        }), 413

    @app.errorhandler(429)
    def _rate_limited(e):
        return jsonify({
            "error": "Too many requests. Please slow down.",
            "code": "rate_limited",
            "details": str(e.description) if hasattr(e, "description") else None,
        }), 429

    register_error_handlers(app)

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    port = int(os.getenv("PORT", "5001"))
    app.run(debug=settings.debug, host="0.0.0.0", port=port)  # nosec B104 - dev runner; prod uses gunicorn in a container
