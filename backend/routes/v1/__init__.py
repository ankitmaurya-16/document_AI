"""v1 API blueprints.

Everything is mounted at ``/api/v1``.
"""
from __future__ import annotations

from flask import Flask

from .auth import bp as auth_bp
from .billing import bp as billing_bp
from .chats import bp as chats_bp
from .documents import bp as documents_bp
from .feedback import bp as feedback_bp
from .health import bp as health_bp
from .rag_chat import bp as rag_bp


def register_v1(app: Flask) -> None:
    for bp, prefix in (
        (health_bp, "/api/v1"),
        (auth_bp, "/api/v1/auth"),
        (billing_bp, "/api/v1/billing"),
        (chats_bp, "/api/v1/chats"),
        (documents_bp, "/api/v1/documents"),
        (feedback_bp, "/api/v1/feedback"),
        (rag_bp, "/api/v1"),
    ):
        app.register_blueprint(bp, url_prefix=prefix, name=f"v1_{bp.name}")
