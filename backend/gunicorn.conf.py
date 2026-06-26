"""Gunicorn config.

Loaded via ``gunicorn -c gunicorn.conf.py app:app``. Centralizes worker,
timeout and shutdown tuning so the Dockerfile CMD stays declarative.

``graceful_timeout`` covers clean rollouts: on SIGTERM, gunicorn stops
accepting new connections and lets in-flight requests finish (up to 30s,
enough for the slowest synchronous chat request) before killing workers.
"""
from __future__ import annotations

import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5001')}"
workers = int(os.getenv("GUNICORN_WORKERS", str(max(2, multiprocessing.cpu_count()))))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

accesslog = "-"
errorlog = "-"
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
)


def worker_exit(server, worker):
    """Flush OTel spans before the worker dies so traces aren't lost on rollout."""
    try:
        from opentelemetry import trace  # type: ignore

        provider = trace.get_tracer_provider()
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
    except Exception:
        pass
