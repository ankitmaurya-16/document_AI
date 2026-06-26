"""Shared pytest fixtures: in-memory Mongo via ``mongomock``, a Flask app with
heavy RAG modules stubbed, and a per-test ``client()`` with rate-limits off.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# --- Baseline env -------------------------------------------------------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-do-not-use-in-prod")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("RERANK_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("MAX_UPLOAD_MB", "2")
os.environ.setdefault("PER_USER_STORAGE_MB", "10")
# Effectively disable rate limits during tests.
os.environ["RATE_LIMIT_DEFAULT"] = "10000/second"
os.environ["RATE_LIMIT_AUTH"] = "10000/second"
os.environ["RATE_LIMIT_CHAT"] = "10000/second"
os.environ["RATE_LIMIT_UPLOAD"] = "10000/second"

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "rag"))


# --- Stub the heavy RAG pieces so `app.py` imports cleanly --------------------
def _install_stubs() -> None:
    # Stub sentence-transformers / CrossEncoder etc to avoid model downloads.
    st_mod = types.ModuleType("sentence_transformers")

    class _FakeEncoder:
        def __init__(self, *a, **kw):
            pass

        def encode(self, texts, **kw):  # returns deterministic tiny vectors
            import numpy as np
            return np.asarray([[0.1, 0.2, 0.3] for _ in texts], dtype="float32")

    st_mod.SentenceTransformer = _FakeEncoder  # type: ignore[attr-defined]
    st_mod.CrossEncoder = _FakeEncoder  # type: ignore[attr-defined]
    sys.modules.setdefault("sentence_transformers", st_mod)

    # Stub OpenAI client so no network call happens.
    openai_mod = types.ModuleType("openai")

    class _Completions:
        def create(self, *a, **kw):
            return MagicMock(choices=[MagicMock(message=MagicMock(content="stubbed answer"))])

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *a, **kw):
            self.chat = _Chat()

    openai_mod.OpenAI = _Client  # type: ignore[attr-defined]
    sys.modules.setdefault("openai", openai_mod)


_install_stubs()


# --- Fixtures -----------------------------------------------------------------
@pytest.fixture
def mongo_patch(monkeypatch):
    """Replace the real PyMongo client with mongomock for DB-touching tests."""
    import mongomock

    fake_client = mongomock.MongoClient()

    from rag import database as db_mod

    # Reset module globals and point helpers at the mock DB.
    monkeypatch.setattr(db_mod, "_client", fake_client, raising=False)
    monkeypatch.setattr(db_mod, "_db", fake_client[db_mod.DB_NAME], raising=False)
    monkeypatch.setattr(db_mod, "get_database", lambda: fake_client[db_mod.DB_NAME])
    return fake_client


@pytest.fixture
def app(mongo_patch, monkeypatch):
    """Build a fresh Flask app per-test."""
    # Disable flask-limiter globally for the test session.
    from extensions import limiter

    limiter.enabled = False

    # Prevent retrieve/ingest from doing any real work.
    import rag.retrieve as retrieve_mod
    import rag.generate as generate_mod

    monkeypatch.setattr(
        retrieve_mod, "retrieve_top_chunks", lambda prompt, **kw: [], raising=False
    )
    import numpy as _np

    monkeypatch.setattr(
        retrieve_mod, "embed_query", lambda q: _np.zeros(384, dtype="float32"), raising=False
    )
    monkeypatch.setattr(
        retrieve_mod, "reload_index", lambda **kw: None, raising=False
    )
    monkeypatch.setattr(
        generate_mod, "generate_answer", lambda prompt, chunks, **kw: "stubbed answer",
        raising=False,
    )

    # Import lazily so env patches above apply first.
    from app import create_app
    # Patch the names the route module imported into its namespace.
    from routes.v1 import rag_chat as rag_chat_mod

    monkeypatch.setattr(rag_chat_mod, "retrieve_top_chunks", lambda *a, **kw: [], raising=False)
    monkeypatch.setattr(
        rag_chat_mod,
        "embed_query",
        lambda q: _np.zeros(384, dtype="float32"),
        raising=False,
    )
    monkeypatch.setattr(rag_chat_mod, "reload_index", lambda **kw: None, raising=False)
    monkeypatch.setattr(
        rag_chat_mod, "generate_answer", lambda *a, **kw: "stubbed answer", raising=False
    )
    monkeypatch.setattr(
        rag_chat_mod,
        "generate_answer_stream",
        lambda *a, **kw: iter(["stubbed ", "answer"]),
        raising=False,
    )

    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(client, mongo_patch):
    """Register a fresh user, return Authorization headers and user_id."""
    payload = {
        "name": "Test User",
        "email": "user@example.com",
        "password": "correct-horse-battery-staple",
    }
    rv = client.post("/api/v1/auth/register", json=payload)
    assert rv.status_code == 201, rv.get_json()
    body = rv.get_json()
    return {
        "headers": {"Authorization": f"Bearer {body['token']}"},
        "user_id": body["user"]["_id"],
        "email": body["user"]["email"],
    }
