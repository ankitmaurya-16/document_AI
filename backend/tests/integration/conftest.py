"""Integration fixtures: real Mongo via testcontainers, for behavior mongomock
can't fake (TTL expiry, DuplicateKeyError, aggregation). Skipped if Docker or
testcontainers/pymongo are unavailable.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# --- Hard dependency checks -- skip the whole suite if any are missing. -----
_mongo_container = pytest.importorskip(
    "testcontainers.mongodb",
    reason="testcontainers not installed; skip integration suite",
).MongoDbContainer

if not shutil.which("docker"):
    pytest.skip("docker CLI not available on PATH", allow_module_level=True)


# --- Session-scoped Mongo container ------------------------------------------
@pytest.fixture(scope="session")
def mongo_container():
    # Pin a small, well-known image tag so CI caching is predictable.
    with _mongo_container("mongo:7.0") as mc:
        yield mc


@pytest.fixture
def mongo_uri(mongo_container):
    return mongo_container.get_connection_url()


# --- App bound to the real Mongo ---------------------------------------------
@pytest.fixture
def app(mongo_uri, monkeypatch, tmp_path):
    """Flask app pointed at a real, per-test Mongo DB.

    The top-level ``conftest.py`` supplies the heavy-model + OpenAI stubs we
    still want (nobody runs real LLM calls in CI). We override just the DB
    side: a fresh database name per test keeps runs hermetic.
    """
    import uuid

    db_name = f"itest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    monkeypatch.setenv("MONGODB_DB", db_name)

    # Also isolate uploads so nothing touches the developer's real data dir.
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("UPLOAD_TMP_DIR", str(uploads))

    # Rebuild the Mongo singleton with the new URI.
    from rag import database as db_mod

    monkeypatch.setattr(db_mod, "_client", None, raising=False)
    monkeypatch.setattr(db_mod, "_db", None, raising=False)
    # DB_NAME is a module-level constant; patch it so get_database() opens
    # the per-test DB we just built.
    monkeypatch.setattr(db_mod, "DB_NAME", db_name, raising=False)

    # Disable rate limits and keep the retrieve/ingest stubs from the root
    # conftest — we only want *real DB*, not real OpenAI.
    from extensions import limiter
    limiter.enabled = False

    import rag.retrieve as retrieve_mod
    import rag.generate as generate_mod
    import numpy as _np

    monkeypatch.setattr(
        retrieve_mod, "retrieve_top_chunks", lambda prompt, **kw: [], raising=False
    )
    monkeypatch.setattr(
        retrieve_mod, "embed_query", lambda q: _np.zeros(384, dtype="float32"), raising=False
    )
    monkeypatch.setattr(retrieve_mod, "reload_index", lambda **kw: None, raising=False)
    monkeypatch.setattr(
        generate_mod, "generate_answer", lambda prompt, chunks, **kw: "integration answer",
        raising=False,
    )

    from app import create_app
    from routes.v1 import rag_chat as rag_chat_mod

    monkeypatch.setattr(rag_chat_mod, "retrieve_top_chunks", lambda *a, **kw: [], raising=False)
    monkeypatch.setattr(
        rag_chat_mod, "embed_query", lambda q: _np.zeros(384, dtype="float32"), raising=False
    )
    monkeypatch.setattr(rag_chat_mod, "reload_index", lambda **kw: None, raising=False)
    monkeypatch.setattr(
        rag_chat_mod, "generate_answer", lambda *a, **kw: "integration answer", raising=False
    )
    monkeypatch.setattr(
        rag_chat_mod, "generate_answer_stream",
        lambda *a, **kw: iter(["integration ", "answer"]), raising=False,
    )

    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def mongo_db(app):
    from rag.database import get_database
    return get_database()


@pytest.fixture
def registered_user(client):
    payload = {
        "name": "Integration User",
        "email": "integration@example.com",
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
