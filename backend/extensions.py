"""Shared Flask extension instances (limiter, CORS).

Kept as a module-level singleton so blueprints can decorate with ``@limiter.limit``
without pulling the app into their imports.
"""
from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from rag.auth import optional_auth


def _rate_key() -> str:
    """Rate-limit key: user id when authenticated, IP otherwise."""
    uid = None
    try:
        uid = optional_auth()
    except Exception:
        uid = None
    return f"user:{uid}" if uid else f"ip:{get_remote_address()}"


# Storage backend is in-memory by default. For multi-process prod, swap to
# "redis://..." via RATELIMIT_STORAGE_URI when Redis is available.
limiter = Limiter(
    key_func=_rate_key,
    default_limits=[],  # default applied explicitly in app.py using settings
    headers_enabled=True,
    storage_uri="memory://",
)
