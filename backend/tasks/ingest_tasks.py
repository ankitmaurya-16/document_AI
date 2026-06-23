"""Ingestion task: chunk → embed → FAISS + BM25.

Uses a small job-state store so the client can poll ``/chat/jobs/<id>``. In
sync mode the job is completed by the time ``enqueue_ingest`` returns. In
Celery mode the HTTP request returns immediately with a pending jobId.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from logging_config import get_logger
from metrics import INGESTION_DURATION
from rag.ingest import ingest_files
from rag.retrieve import reload_index
from rag.user_store import add_user_bytes, list_raw_files
from storage import materialize_keys_to_dir

log = get_logger("tasks.ingest")

# --- Job state store -------------------------------------------------------
#
# Uses the shared cache backend if available (Redis or memory). This means
# jobs survive across workers in prod (Redis) but not across process restarts
# in dev (memory). A persistent store is the eventual home for this.

from cache import _b, _key  # noqa: E402


@dataclass
class JobState:
    id: str
    status: str  # pending | running | succeeded | failed
    user_id: Optional[str]
    files: list[str] = field(default_factory=list)
    error: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0


def _job_key(job_id: str) -> str:
    return _key(["job", job_id])


def _save(state: JobState) -> None:
    _b().set(_job_key(state.id), json.dumps(asdict(state)), ttl=60 * 60 * 24)


def _load(job_id: str) -> Optional[JobState]:
    raw = _b().get(_job_key(job_id))
    if not raw:
        return None
    try:
        return JobState(**json.loads(raw))
    except (ValueError, TypeError):
        return None


# --- Task body -------------------------------------------------------------


def _run_ingest(job_id: str, file_paths: list[str], total_bytes: int, user_id: Optional[str]):
    state = _load(job_id) or JobState(id=job_id, status="pending", user_id=user_id)
    state.status = "running"
    state.started_at = time.time()
    _save(state)
    materialized_dir: Optional[tempfile.TemporaryDirectory] = None
    ingest_t0 = time.time()
    try:
        # Re-ingest the user's whole corpus so retrieval stays consistent after
        # uploads/deletions. Authenticated uploads are already saved to the raw
        # store (under their original names) before this runs, so ingest from
        # there; indexing the temp paths too would duplicate each doc under its
        # "{user}__{uuid}__name" temp filename. Anonymous uploads aren't
        # persisted, so fall back to the temp batch. (S3 keys download first.)
        existing_keys = list_raw_files(user_id) if user_id else []
        if existing_keys:
            materialized_dir = tempfile.TemporaryDirectory(prefix="docai_existing_")
            existing_local = materialize_keys_to_dir(existing_keys, materialized_dir.name)
        else:
            existing_local = []
        sources = existing_local if user_id else list(file_paths)
        ingest_files(sources or list(file_paths), user_id=user_id)
        reload_index(user_id=user_id)
        if user_id:
            add_user_bytes(user_id, total_bytes)
        state.status = "succeeded"
    except Exception as e:
        log.exception("ingest.job_failed", job_id=job_id, error=str(e))
        state.status = "failed"
        state.error = str(e)
    finally:
        if materialized_dir is not None:
            materialized_dir.cleanup()
        state.finished_at = time.time()
        INGESTION_DURATION.observe(state.finished_at - ingest_t0)
        _save(state)
        # Only remove tmp upload paths, not the persistent raw/ store.
        for p in file_paths:
            if "/raw/" in p or p.endswith("/raw"):
                continue
            try:
                os.remove(p)
            except OSError:
                pass


# --- Celery wiring (lazy) --------------------------------------------------

_celery_task = None


def _record_dead_letter(job_id: str, exc: BaseException, user_id: Optional[str]) -> None:
    """Persist a final-failure record so ops can inspect / replay manually."""
    try:
        from datetime import datetime

        from rag.database import get_database

        get_database().failed_ingests.insert_one({
            "job_id": job_id,
            "user_id": user_id,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "failed_at": datetime.utcnow(),
        })
    except Exception as db_err:  # never let DLQ logging mask the real failure
        log.warning("ingest.dlq_persist_failed", job_id=job_id, error=str(db_err))


def _register_celery_task():
    global _celery_task
    if _celery_task is not None:
        return _celery_task
    from celery import Task  # type: ignore

    from tasks.celery_app import get_celery

    app = get_celery()
    if app is None:
        return None

    # Retry on transient external failures only — bad files / unsupported
    # formats raise ValueError and should fail fast (no point retrying).
    try:
        from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError
        _RETRY_TYPES: tuple = (
            APIError, APIConnectionError, APITimeoutError, RateLimitError, ConnectionError,
        )
    except ImportError:
        _RETRY_TYPES = (ConnectionError,)

    class _IngestTask(Task):
        """Routes any final failure (non-retryable, or retries exhausted) to a DLQ collection."""

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            job_id = (args[0] if args else kwargs.get("job_id")) or task_id
            user_id = args[3] if len(args) >= 4 else kwargs.get("user_id")
            _record_dead_letter(job_id, exc, user_id)
            super().on_failure(exc, task_id, args, kwargs, einfo)

    @app.task(
        name="tasks.ingest.run",
        base=_IngestTask,
        bind=True,
        autoretry_for=_RETRY_TYPES,
        retry_backoff=True,
        retry_backoff_max=60,
        retry_jitter=True,
        retry_kwargs={"max_retries": 5},
        acks_late=True,
    )
    def _task(self, job_id: str, file_paths: list[str], total_bytes: int, user_id: Optional[str]):
        _run_ingest(job_id, file_paths, total_bytes, user_id)

    _celery_task = _task
    return _task


# --- Public API ------------------------------------------------------------


def enqueue_ingest(
    *, file_paths: list[str], total_bytes: int, user_id: Optional[str]
) -> str:
    """Register a new job and schedule ingestion. Returns the job id."""
    from tasks import ASYNC_MODE

    job_id = uuid.uuid4().hex
    state = JobState(
        id=job_id, status="pending", user_id=user_id, files=[os.path.basename(p) for p in file_paths]
    )
    _save(state)
    log.info("ingest.enqueued", job_id=job_id, files=len(file_paths), mode=ASYNC_MODE)

    if ASYNC_MODE == "celery":
        task = _register_celery_task()
        if task is not None:
            task.delay(job_id, file_paths, total_bytes, user_id)
            return job_id
        log.warning("ingest.celery_unavailable_running_sync")

    _run_ingest(job_id, file_paths, total_bytes, user_id)
    return job_id


def get_job_status(job_id: str) -> Optional[dict]:
    state = _load(job_id)
    if not state:
        return None
    return asdict(state)
