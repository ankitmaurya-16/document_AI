"""Feedback endpoint tests."""
from __future__ import annotations


def test_feedback_requires_auth(client):
    rv = client.post("/api/v1/feedback", json={
        "chatId": "c1", "messageTimestamp": 1.0, "rating": 1,
    })
    assert rv.status_code == 401


def test_feedback_upvote_persisted(client, auth_headers, mongo_patch):
    rv = client.post(
        "/api/v1/feedback",
        json={"chatId": "chat-1", "messageTimestamp": 123.0, "rating": 1},
        headers=auth_headers["headers"],
    )
    assert rv.status_code == 201
    body = rv.get_json()
    assert body["rating"] == 1
    assert body["chatId"] == "chat-1"

    db = mongo_patch["rag_chat_app"]
    stored = list(db.feedback.find({}))
    assert len(stored) == 1
    assert stored[0]["userId"] == auth_headers["user_id"]


def test_feedback_upsert_replaces_prior_rating(client, auth_headers, mongo_patch):
    payload = {"chatId": "chat-1", "messageTimestamp": 99.0, "rating": 1}
    client.post("/api/v1/feedback", json=payload, headers=auth_headers["headers"])
    payload["rating"] = -1
    client.post("/api/v1/feedback", json=payload, headers=auth_headers["headers"])

    db = mongo_patch["rag_chat_app"]
    stored = list(db.feedback.find({}))
    assert len(stored) == 1
    assert stored[0]["rating"] == -1


def test_feedback_rejects_invalid_rating(client, auth_headers):
    rv = client.post(
        "/api/v1/feedback",
        json={"chatId": "c", "messageTimestamp": 1.0, "rating": 5},
        headers=auth_headers["headers"],
    )
    assert rv.status_code == 400
