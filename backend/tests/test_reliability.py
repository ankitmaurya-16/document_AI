"""Reliability & security unit tests: PII redaction, security headers, Stripe
webhook idempotency, and the retry decorator. No real external services.
"""
from __future__ import annotations

import pytest


# --- PII redaction ---------------------------------------------------------


def test_pii_redaction_scrubs_emails_and_tokens():
    from logging_config import _redact_pii

    out = _redact_pii(
        None,
        "info",
        {
            "event": "login",
            "email": "alice@example.com",
            "auth": "Bearer abc.def.ghi",
            "card": "4242 4242 4242 4242",
            "nested": {"user_email": "bob@b.com"},
            "untouched": 42,
        },
    )
    assert out["email"] == "<redacted>"
    assert out["auth"] == "Bearer <redacted>"
    assert out["card"] == "<redacted>"
    assert out["nested"]["user_email"] == "<redacted>"
    assert out["untouched"] == 42
    assert out["event"] == "login"


# --- Security headers ------------------------------------------------------


def test_security_headers_present_on_every_response(client):
    rv = client.get("/api/v1/health")
    h = rv.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy", "").startswith("strict-origin")
    assert "default-src 'self'" in h.get("Content-Security-Policy", "")
    # HSTS only over HTTPS — test client is HTTP, so it must NOT be set.
    assert "Strict-Transport-Security" not in h


# --- Retry decorator -------------------------------------------------------


def test_with_retry_increments_counter_and_reraises(monkeypatch):
    from resilience import with_retry

    calls: list[int] = []

    @with_retry("openai", exception_types=(ValueError,), attempts=3, max_wait=0.01)
    def flaky():
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        flaky()
    assert len(calls) == 3  # 3 attempts before giving up


def test_with_retry_succeeds_after_one_failure():
    from resilience import with_retry

    state = {"n": 0}

    @with_retry("openai", exception_types=(ValueError,), attempts=3, max_wait=0.01)
    def eventually_ok():
        state["n"] += 1
        if state["n"] < 2:
            raise ValueError("transient")
        return "ok"

    assert eventually_ok() == "ok"
    assert state["n"] == 2


def test_with_retry_does_not_retry_unlisted_exceptions():
    from resilience import with_retry

    calls: list[int] = []

    @with_retry("openai", exception_types=(ValueError,), attempts=3, max_wait=0.01)
    def wrong_kind():
        calls.append(1)
        raise TypeError("not retried")

    with pytest.raises(TypeError):
        wrong_kind()
    assert len(calls) == 1


# --- Stripe webhook idempotency -------------------------------------------


def test_processed_events_index_is_unique(mongo_patch):
    from routes.v1.billing import _ensure_processed_events_index

    db = mongo_patch[__import__("rag.database", fromlist=["DB_NAME"]).DB_NAME]
    _ensure_processed_events_index(db)
    db.processed_events.insert_one({"event_id": "evt_1", "type": "checkout.session.completed"})
    from pymongo.errors import DuplicateKeyError
    with pytest.raises(DuplicateKeyError):
        db.processed_events.insert_one({"event_id": "evt_1", "type": "checkout.session.completed"})
