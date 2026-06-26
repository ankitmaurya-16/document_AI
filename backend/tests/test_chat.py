"""Chat endpoint tests (RAG is stubbed — we verify the HTTP layer and persistence)."""
from __future__ import annotations


def test_chat_anonymous_returns_answer(client):
    rv = client.post("/api/v1/chat", json={"prompt": "Hello"})
    assert rv.status_code == 200
    body = rv.get_json()
    assert "response" in body


def test_chat_persists_messages_for_authed_user(client, auth_headers, mongo_patch):
    rv = client.post(
        "/api/v1/chat",
        json={"prompt": "What is RAG?"},
        headers=auth_headers["headers"],
    )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["chatId"]

    # Verify Mongo has the chat + messages.
    db = mongo_patch["rag_chat_app"]
    chats = list(db.chats.find({"userId": auth_headers["user_id"]}))
    assert len(chats) == 1
    assert len(chats[0]["messages"]) == 2
    roles = [m["role"] for m in chats[0]["messages"]]
    assert roles == ["user", "assistant"]


def test_chat_rejects_missing_prompt(client):
    rv = client.post("/api/v1/chat", json={})
    assert rv.status_code == 400


def test_chat_rejects_non_json(client):
    rv = client.post("/api/v1/chat", data="prompt=hi", content_type="application/x-www-form-urlencoded")
    assert rv.status_code == 400


def test_chat_rejects_extra_fields(client):
    rv = client.post("/api/v1/chat", json={"prompt": "hi", "model": "gpt-4"})
    assert rv.status_code == 400
