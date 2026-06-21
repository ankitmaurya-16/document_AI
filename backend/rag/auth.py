"""Authentication: JWT issuance/verification and password hashing.

- Secret is pulled from ``settings.get_settings()`` (no hard-coded fallback);
  it fails fast in production if the env var is missing.
- Default access-token TTL is one week, with a separate refresh-token helper
  so the access token can be shortened later without breaking callers.
- ``require_auth`` raises ``AuthError`` so error handling is centralized.
- ``jwt.InvalidTokenError`` is caught specifically; unexpected errors bubble up.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, Tuple

import bcrypt
import jwt
from flask import request

from errors import AuthError
from logging_config import get_logger
from settings import get_settings

log = get_logger("auth")

_MIN_PASSWORD_LEN = 8  # was 6; bump to a saner default
_MIN_NAME_LEN = 2


def _cfg():
    return get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_token(user_id: str, email: str, *, ttl_hours: int | None = None) -> str:
    cfg = _cfg()
    now = datetime.now(timezone.utc)
    exp_hours = ttl_hours if ttl_hours is not None else cfg.jwt_expiration_hours
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(hours=exp_hours),
        "typ": "access",
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def generate_refresh_token(user_id: str, email: str) -> str:
    cfg = _cfg()
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=30),
        "typ": "refresh",
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_token(token: str, *, expected_type: str = "access") -> Optional[dict]:
    cfg = _cfg()
    try:
        payload = jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        log.info("jwt.expired")
        return None
    except jwt.InvalidTokenError as e:
        log.info("jwt.invalid", error=str(e))
        return None

    if payload.get("typ") != expected_type:
        log.info("jwt.wrong_type", got=payload.get("typ"), want=expected_type)
        return None
    return payload


def get_token_from_header() -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip() or None
    return None


def require_auth(f):
    """Decorator: 401 if no/invalid token; otherwise sets request.user_id/email."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token_from_header()
        if not token:
            raise AuthError("Authentication required", code="missing_token")

        payload = decode_token(token)
        if not payload:
            raise AuthError("Invalid or expired token", code="invalid_token")

        request.user_id = payload.get("user_id")
        request.user_email = payload.get("email")
        return f(*args, **kwargs)

    return wrapper


def optional_auth():
    """Non-decorator helper: returns user_id if a valid token is present, else None."""
    token = get_token_from_header()
    if not token:
        return None
    payload = decode_token(token)
    return payload.get("user_id") if payload else None


def register_user(name: str, email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import create_user, get_user_by_email

    if not name or len(name.strip()) < _MIN_NAME_LEN:
        return None, f"Name must be at least {_MIN_NAME_LEN} characters"
    if len(password) < _MIN_PASSWORD_LEN:
        return None, f"Password must be at least {_MIN_PASSWORD_LEN} characters"

    if get_user_by_email(email):
        return None, "Email already registered"

    user = create_user(name.strip(), email.lower().strip(), hash_password(password))
    token = generate_token(user["_id"], email)
    log.info("user.registered", user_id=user["_id"])
    return {"user": user, "token": token}, None


def login_user(email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import get_user_by_email

    user = get_user_by_email(email.lower().strip())
    # Constant-time-ish: run bcrypt even if user missing, to reduce user-existence oracle.
    stored = user["password"] if user and "password" in user else bcrypt.hashpw(
        b"dummy", bcrypt.gensalt()
    ).decode("utf-8")
    ok = verify_password(password, stored)

    if not user or not user.get("password") or not ok:
        log.info("login.failed", email_hash=hash(email))
        return None, "Invalid email or password"

    user_data = {k: v for k, v in user.items() if k != "password"}
    token = generate_token(user["_id"], email)
    log.info("login.success", user_id=user["_id"])
    return {"user": user_data, "token": token}, None


def verify_user_token(token: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import get_user_by_id

    payload = decode_token(token)
    if not payload:
        return None, "Invalid or expired token"
    user = get_user_by_id(payload.get("user_id"))
    if not user:
        return None, "User not found"
    return user, None
