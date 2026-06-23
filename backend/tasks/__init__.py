"""Celery background workers for ingestion.

``ASYNC_MODE`` selects ``sync`` (inline, default) or ``celery`` (worker; needs
``CELERY_BROKER_URL``). The public API is the same in both modes.
"""
from __future__ import annotations

import os

ASYNC_MODE = os.getenv("ASYNC_MODE", "sync").lower()

from .ingest_tasks import enqueue_ingest, get_job_status  # noqa: E402

__all__ = ["ASYNC_MODE", "enqueue_ingest", "get_job_status"]
