"""Auth endpoint tests."""
from __future__ import annotations


def test_register_happy_path(client, mongo_patch):
    rv = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "longenough1"},
    )
    assert rv.status_code == 201
    body = rv.get_json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["credits"] == 100
    assert "token" in body and len(body["token"]) > 20
    assert "password" not in body["user"]


def test_register_rejects_weak_password(client, mongo_patch):
    rv = client.post(
        "/api/v1/auth/register",
        json={"name": "Alice", "email": "a@b.com", "password": "short"},
    )
    assert rv.status_code == 400
    assert "error" in rv.get_json()


def test_register_rejects_duplicate_email(client, mongo_patch):
    payload = {"name": "Alice", "email": "dup@example.com", "password": "longenough1"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 400


def test_register_rejects_extra_fields(client, mongo_patch):
    rv = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Alice",
            "email": "a@b.com",
            "password": "longenough1",
            "role": "admin",  # extra field should be rejected
        },
    )
    assert rv.status_code == 400


def test_login_happy_path(client, mongo_patch):
    client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob@example.com", "password": "correcthorse"},
    )
    rv = client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "correcthorse"},
    )
    assert rv.status_code == 200
    assert "token" in rv.get_json()


def test_login_wrong_password(client, mongo_patch):
    client.post(
        "/api/v1/auth/register",
        json={"name": "Bob", "email": "bob2@example.com", "password": "correcthorse"},
    )
    rv = client.post(
        "/api/v1/auth/login",
        json={"email": "bob2@example.com", "password": "wrongpassword"},
    )
    assert rv.status_code == 401


def test_verify_requires_token(client):
    rv = client.get("/api/v1/auth/verify")
    assert rv.status_code == 401


def test_verify_with_valid_token(client, auth_headers):
    rv = client.get("/api/v1/auth/verify", headers=auth_headers["headers"])
    assert rv.status_code == 200
    assert rv.get_json()["user"]["_id"] == auth_headers["user_id"]


def test_legacy_alias_removed(client, mongo_patch):
    # The /api/* alias was dropped; only /api/v1/* is routed now.
    rv = client.post(
        "/api/auth/register",
        json={"name": "Legacy", "email": "legacy@example.com", "password": "longenough1"},
    )
    assert rv.status_code == 404
