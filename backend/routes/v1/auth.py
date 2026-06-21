"""Auth endpoints: register, login, verify, Google OAuth."""
from __future__ import annotations

import requests as http_requests
from flask import Blueprint, jsonify, request

from errors import AuthError, ValidationError
from extensions import limiter
from logging_config import get_logger
from rag.auth import (
    decode_token,
    generate_token,
    get_token_from_header,
    login_user,
    register_user,
    verify_user_token,
)
from rag.database import (
    create_user,
    get_user_by_email,
    update_user_provider,
)
from schemas import GoogleAuthIn, LoginIn, RegisterIn, parse_json
from settings import get_settings

bp = Blueprint("auth", __name__)
log = get_logger("routes.auth")


@bp.post("/register")
@limiter.limit(lambda: get_settings().rate_limit_auth)
def register():
    payload = parse_json(RegisterIn, request)
    result, err = register_user(payload.name, payload.email, payload.password)
    if err:
        raise ValidationError(err)
    return jsonify(result), 201


@bp.post("/login")
@limiter.limit(lambda: get_settings().rate_limit_auth)
def login():
    payload = parse_json(LoginIn, request)
    result, err = login_user(payload.email, payload.password)
    if err:
        raise AuthError(err, code="invalid_credentials")
    return jsonify(result), 200


@bp.get("/verify")
@limiter.limit(lambda: get_settings().rate_limit_default)
def verify():
    token = get_token_from_header()
    if not token:
        raise AuthError("No token provided", code="missing_token")
    user, err = verify_user_token(token)
    if err:
        raise AuthError(err, code="invalid_token")
    return jsonify({"user": user}), 200


@bp.post("/google")
@limiter.limit(lambda: get_settings().rate_limit_auth)
def google_auth():
    payload = parse_json(GoogleAuthIn, request)
    resp = http_requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {payload.access_token}"},
        timeout=5,
    )
    if resp.status_code != 200:
        raise AuthError("Invalid Google token", code="invalid_oauth_token")

    google_user = resp.json()
    email = google_user.get("email")
    google_id = google_user.get("sub")
    if not email:
        raise ValidationError("Google response missing email")

    name = google_user.get("name") or email.split("@")[0]
    existing = get_user_by_email(email)

    if existing:
        if existing.get("provider") != "google":
            update_user_provider(existing["_id"], "google", google_id)
        user_id = existing["_id"]
        user_data = {
            "_id": user_id,
            "name": existing["name"],
            "email": existing["email"],
            "credits": existing.get("credits", 100),
        }
    else:
        new_user = create_user(name, email, None, provider="google", provider_id=google_id)
        user_id = new_user["_id"]
        user_data = {
            "_id": user_id,
            "name": new_user["name"],
            "email": new_user["email"],
            "credits": new_user.get("credits", 100),
        }

    token = generate_token(user_id, email)
    log.info("oauth.google.success", user_id=user_id)
    return jsonify({"token": token, "user": user_data}), 200


# Exposed for rate-limit key function in extensions.py
__all__ = ["bp", "decode_token"]
