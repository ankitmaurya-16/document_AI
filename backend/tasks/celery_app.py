"""Celery app factory.

Imported lazily: the Celery package itself is optional — if it's missing or
the broker URL isn't set, the task module falls back to synchronous execution.
"""
from __future__ import annotations

import os
from typing import Optional

from logging_config import get_logger

log = get_logger("celery")

_app = None


def get_celery():
    global _app
    if _app is not None:
        return _app

    broker = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
    backend = os.getenv("CELERY_RESULT_BACKEND") or broker
    if not broker:
        log.info("celery.disabled", reason="no_broker_url")
        return None

    try:
        from celery import Celery  # type: ignore
    except ImportError:
        log.warning("celery.missing_dependency", hint="pip install celery[redis]")
        return None

    _app = Celery("docai", broker=broker, backend=backend, include=["tasks.ingest_tasks"])
    _app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_time_limit=60 * 15,
        task_soft_time_limit=60 * 13,
    )
    _install_shutdown_handler()
    log.info("celery.enabled", broker=broker)
    return _app


def _install_shutdown_handler() -> None:
    """On worker SIGTERM, flush OTel spans and close the Qdrant client."""
    try:
        from celery.signals import worker_shutting_down  # type: ignore
    except ImportError:
        return

    @worker_shutting_down.connect
    def _shutdown(*_args, **_kwargs):  # noqa: ANN001
        try:
            from opentelemetry import trace  # type: ignore

            shutdown = getattr(trace.get_tracer_provider(), "shutdown", None)
            if callable(shutdown):
                shutdown()
        except Exception:
            pass
        try:
            from rag.vector_store import _store

            client = getattr(_store, "_client", None) if _store else None
            close = getattr(client, "close", None)
            if callable(close):
                close()
        except Exception:
            pass


# Convenience alias so ``celery -A tasks.celery_app`` discovers the app object.
celery_app: Optional[object] = get_celery()
