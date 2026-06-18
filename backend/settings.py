"""Application settings from environment, with fail-fast validation.

In production any missing required secret raises at startup; in development we
fall back to dev defaults (never a production-safe default for privileged values).
Secrets go through the pluggable ``SecretProvider`` so Vault/AWS can slot in later.
"""
from __future__ import annotations

import os
import secrets as _secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, name: str, default: str | None = None) -> str | None: ...


class EnvSecretProvider:
    """Default: read from process env. Works with .env, ECS task vars, k8s secrets."""

    def get(self, name: str, default: str | None = None) -> str | None:
        return os.getenv(name, default)


# TODO: VaultSecretProvider / AWSSecretsManagerProvider, selected via APP_SECRET_PROVIDER.
_secret_provider: SecretProvider = EnvSecretProvider()


def set_secret_provider(provider: SecretProvider) -> None:
    global _secret_provider
    _secret_provider = provider


def _require(name: str, *, env: str) -> str:
    value = _secret_provider.get(name)
    if value is None or value.strip() == "":
        if env == "production":
            raise RuntimeError(
                f"Missing required secret {name!r} in production. "
                f"Set it in your environment / secrets manager."
            )
        # Dev fallback: generate an ephemeral random value so nothing insecure is hard-coded.
        # A warning is printed so this is obvious.
        fallback = _secrets.token_urlsafe(32)
        print(
            f"[settings] WARNING: {name} not set — using ephemeral dev value. "
            "Do NOT rely on this across restarts.",
            flush=True,
        )
        return fallback
    return value


def _optional(name: str, default: str | None = None) -> str | None:
    return _secret_provider.get(name, default)


def _bool(name: str, default: bool = False) -> bool:
    raw = _optional(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = _optional(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    # Env
    app_env: str  # "development" | "production" | "test"
    debug: bool

    # Security
    jwt_secret: str
    jwt_algorithm: str
    jwt_expiration_hours: int

    # Datastore
    mongodb_uri: str
    db_name: str

    # OpenAI
    openai_api_key: str

    # OAuth
    google_client_id: str | None
    google_client_secret: str | None

    # HTTP
    cors_allowed_origins: tuple[str, ...]
    max_upload_mb: int
    max_files_per_request: int
    per_user_storage_mb: int

    # Observability
    log_level: str
    json_logs: bool
    sentry_dsn: str | None
    sentry_traces_sample_rate: float

    # Rate limits (per IP unless noted)
    rate_limit_default: str
    rate_limit_auth: str
    rate_limit_chat: str
    rate_limit_upload: str

    @property
    def is_prod(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = (_optional("APP_ENV", "development") or "development").lower()

    origins_raw = _optional("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000") or ""
    origins = tuple(o.strip() for o in origins_raw.split(",") if o.strip())
    if env == "production" and ("*" in origins or not origins):
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must be an explicit comma-separated list in production "
            "(not '*' or empty)."
        )

    settings = Settings(
        app_env=env,
        debug=_bool("FLASK_DEBUG", env != "production"),
        jwt_secret=_require("JWT_SECRET", env=env),
        jwt_algorithm=_optional("JWT_ALGORITHM", "HS256") or "HS256",
        jwt_expiration_hours=_int("JWT_EXPIRATION_HOURS", 24 * 7),
        mongodb_uri=_require("MONGODB_URI", env=env),
        db_name=_optional("DB_NAME", "rag_chat_app") or "rag_chat_app",
        openai_api_key=_require("OPENAI_API_KEY", env=env),
        google_client_id=_optional("VITE_GOOGLE_CLIENT_ID"),
        google_client_secret=_optional("GOOGLE_CLIENT_SECRET"),
        cors_allowed_origins=origins,
        max_upload_mb=_int("MAX_UPLOAD_MB", 16),
        max_files_per_request=_int("MAX_FILES_PER_REQUEST", 10),
        per_user_storage_mb=_int("PER_USER_STORAGE_MB", 200),
        log_level=_optional("LOG_LEVEL", "INFO") or "INFO",
        json_logs=_bool("LOG_JSON", env == "production"),
        sentry_dsn=_optional("SENTRY_DSN"),
        sentry_traces_sample_rate=float(_optional("SENTRY_TRACES_SAMPLE_RATE", "0.1") or "0.1"),
        rate_limit_default=_optional("RATE_LIMIT_DEFAULT", "200/hour") or "200/hour",
        rate_limit_auth=_optional("RATE_LIMIT_AUTH", "10/minute") or "10/minute",
        rate_limit_chat=_optional("RATE_LIMIT_CHAT", "30/minute") or "30/minute",
        rate_limit_upload=_optional("RATE_LIMIT_UPLOAD", "10/minute") or "10/minute",
    )
    return settings
