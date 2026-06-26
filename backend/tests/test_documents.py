"""Documents endpoint tests (list + delete). Ingestion itself is stubbed."""
from __future__ import annotations

from unittest.mock import patch


def test_list_requires_auth(client):
    rv = client.get("/api/v1/documents")
    assert rv.status_code == 401


def test_list_returns_user_docs(client, auth_headers, mongo_patch):
    db = mongo_patch["rag_chat_app"]
    db.documents.insert_one({
        "userId": auth_headers["user_id"],
        "filename": "a.pdf",
        "size": 1234,
        "rawPath": "/tmp/should_not_leak.pdf",
    })
    rv = client.get("/api/v1/documents", headers=auth_headers["headers"])
    assert rv.status_code == 200
    body = rv.get_json()
    assert len(body["documents"]) == 1
    assert body["documents"][0]["filename"] == "a.pdf"
    # Server-side paths must never leak.
    assert "rawPath" not in body["documents"][0]


def test_delete_document(client, auth_headers, mongo_patch):
    db = mongo_patch["rag_chat_app"]
    r = db.documents.insert_one({
        "userId": auth_headers["user_id"],
        "filename": "a.pdf",
        "size": 10,
        "rawPath": "/tmp/nonexistent.pdf",
    })
    doc_id = str(r.inserted_id)
    with patch("routes.v1.documents.ingest_files"), \
         patch("routes.v1.documents.reload_index"), \
         patch("routes.v1.documents.list_raw_files", return_value=[]), \
         patch("routes.v1.documents.remove_raw_file", return_value=True), \
         patch("routes.v1.documents.wipe_namespace"):
        rv = client.delete(f"/api/v1/documents/{doc_id}", headers=auth_headers["headers"])
    assert rv.status_code == 200
    assert db.documents.count_documents({}) == 0


def test_delete_foreign_document_denied(client, auth_headers, mongo_patch):
    db = mongo_patch["rag_chat_app"]
    r = db.documents.insert_one({
        "userId": "some-other-user",
        "filename": "secret.pdf",
        "size": 10,
    })
    rv = client.delete(f"/api/v1/documents/{r.inserted_id}", headers=auth_headers["headers"])
    assert rv.status_code == 404
    assert db.documents.count_documents({}) == 1
