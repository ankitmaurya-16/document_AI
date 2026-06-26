"""Bounded retries for external calls (OpenAI, Stripe, Qdrant, S3): 3 attempts,
exponential backoff capped at 10s, only on the exception types the caller
declares. Each retry bumps ``docai_external_retry_total``. No-op without tenacity.
"""
from __future__ import annotations

from typing import Callable, Tuple, Type

from logging_config import get_logger
from metrics import EXTERNAL_RETRY

log = get_logger("resilience")


def with_retry(
    service: str,
    *,
    exception_types: Tuple[Type[BaseException], ...],
    attempts: int = 3,
    max_wait: float = 10.0,
) -> Callable:
    """Retry ``exception_types`` with exponential backoff; ``service`` labels the metric."""
    try:
        from tenacity import (
            before_sleep_log,
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )
    except ImportError:
        log.info("resilience.tenacity_missing", hint="pip install tenacity")

        def _passthrough(fn: Callable) -> Callable:
            return fn

        return _passthrough

    import logging

    def _bump_counter(retry_state) -> None:
        EXTERNAL_RETRY.labels(service=service).inc()

    return retry(
        reraise=True,
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, max=max_wait),
        retry=retry_if_exception_type(exception_types),
        before_sleep=lambda rs: (
            _bump_counter(rs),
            before_sleep_log(logging.getLogger("resilience"), logging.WARNING)(rs),
        )[-1],
    )
