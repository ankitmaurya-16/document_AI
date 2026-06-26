"""End-to-end: register → doc insert → chat → feedback → delete.

Exercises the full HTTP surface against a real Mongo container. Retrieval +
LLM remain stubbed — we're proving the *wiring* works, not the ML quality
(that's [evals/](../../evals/)).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_register_chat_feedback_lifecycle(client, registered_user, mongo_db):
    headers = registered_user["headers"]

    # 1. A chat turn persists (our stub returns "integration answer").
    rv = client.post(
        "/api/v1/chat",
        json={"prompt": "Hello?"},
        headers=headers,
    )
    assert rv.status_code == 200, rv.get_json()
    body = rv.get_json()
    assert body["response"] == "integration answer"
    chat_id = body["chatId"]

    # Chat landed in Mongo under the current user.
    chats = list(mongo_db.chats.find({"userId": registered_user["user_id"]}))
    assert len(chats) == 1
    assert str(chats[0]["_id"]) == chat_id
    assert len(chats[0]["messages"]) == 2  # user + assistant

    # 2. Give a thumbs-up on the assistant reply → feedback row written.
    assistant = next(m for m in chats[0]["messages"] if m["role"] == "assistant")
    rv = client.post(
        "/api/v1/feedback",
        json={"chatId": chat_id, "messageTimestamp": assistant["timestamp"], "rating": 1},
        headers=headers,
    )
    assert rv.status_code == 201
    fb = list(mongo_db.feedback.find({}))
    assert len(fb) == 1
    assert fb[0]["rating"] == 1

    # 3. Toggle the rating — upsert replaces the prior row.
    rv = client.post(
        "/api/v1/feedback",
        json={"chatId": chat_id, "messageTimestamp": assistant["timestamp"], "rating": 0},
        headers=headers,
    )
    assert rv.status_code in (200, 201)
    fb = list(mongo_db.feedback.find({}))
    assert len(fb) == 1
    assert fb[0]["rating"] == 0


def test_document_delete_denies_cross_user(client, registered_user, mongo_db):
    # Insert a doc belonging to someone else, then try to delete as our user.
    other_id = mongo_db.documents.insert_one({
        "userId": "some-other-user",
        "filename": "secret.pdf",
        "size": 10,
    }).inserted_id

    rv = client.delete(
        f"/api/v1/documents/{other_id}",
        headers=registered_user["headers"],
    )
    assert rv.status_code == 404
    # The victim's doc is untouched.
    assert mongo_db.documents.count_documents({"_id": other_id}) == 1


def test_auth_required_on_protected_routes(client):
    # No token → 401 across the board.
    assert client.get("/api/v1/documents").status_code == 401
    assert client.post("/api/v1/chat", json={"prompt": "x"}).status_code == 401
    assert client.post(
        "/api/v1/feedback",
        json={"chatId": "c", "messageTimestamp": 1.0, "rating": 1},
    ).status_code == 401
