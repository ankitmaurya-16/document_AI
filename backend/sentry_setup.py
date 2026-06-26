"""Optional Sentry integration.

Activated only when SENTRY_DSN is present. No-op otherwise so local dev
does not require the dependency at runtime.
"""
from __future__ import annotations

from logging_config import get_logger
from settings import Settings

log = get_logger("sentry")


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        log.info("sentry.disabled", reason="no_dsn")
        return

    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.flask import FlaskIntegration  # type: ignore
    except ImportError:
        log.warning("sentry.missing_dependency", hint="pip install sentry-sdk[flask]")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.app_env,
        send_default_pii=False,
    )
    log.info("sentry.enabled", env=settings.app_env)
