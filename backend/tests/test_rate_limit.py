"""Smoke test that the limiter is wired up (per-user / per-IP key)."""
from __future__ import annotations

from unittest.mock import patch

from extensions import _rate_key


def test_rate_key_prefers_user_id(app):
    with app.test_request_context("/"):
        with patch("extensions.optional_auth", return_value="u-42"):
            key = _rate_key()
    assert key == "user:u-42"


def test_rate_key_falls_back_to_ip(app):
    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "198.51.100.7"}):
        with patch("extensions.optional_auth", return_value=None):
            key = _rate_key()
    assert key.startswith("ip:") and "198.51.100.7" in key


def test_limiter_settings_loaded():
    from settings import get_settings

    s = get_settings()
    assert s.rate_limit_auth
    assert s.rate_limit_chat
