"""HTTP security headers: OWASP baseline plus a strict same-origin CSP. HSTS is
only sent over HTTPS so local http dev isn't pinned to TLS.
"""
from __future__ import annotations

from flask import Flask, request

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

_HSTS = "max-age=31536000; includeSubDomains"


def install_security_headers(app: Flask) -> None:
    @app.after_request
    def _set_headers(response):
        for k, v in _BASE_HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers.setdefault("Content-Security-Policy", _CSP)
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", _HSTS)
        return response
