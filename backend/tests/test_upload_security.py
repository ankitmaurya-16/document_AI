"""Upload validation tests — extension, size, magic-byte sniff."""
from __future__ import annotations

import io

import pytest
from werkzeug.datastructures import FileStorage

from security import validate_uploads
from errors import ValidationError


def _fs(name: str, content: bytes) -> FileStorage:
    return FileStorage(stream=io.BytesIO(content), filename=name)


def test_rejects_disallowed_extension(app):
    with app.app_context(), pytest.raises(ValidationError):
        validate_uploads(
            [_fs("evil.exe", b"MZ\x90\x00" + b"\x00" * 100)],
            user_id="u1",
            current_user_bytes=0,
        )


def test_rejects_empty_file(app):
    with app.app_context(), pytest.raises(ValidationError):
        validate_uploads(
            [_fs("blank.pdf", b"")], user_id="u1", current_user_bytes=0
        )


def test_rejects_oversize_file(app):
    # Per env in conftest MAX_UPLOAD_MB=2 → reject 3MB pdf.
    big = b"%PDF-" + b"\x00" * (3 * 1024 * 1024)
    with app.app_context(), pytest.raises(ValidationError):
        validate_uploads([_fs("huge.pdf", big)], user_id="u1", current_user_bytes=0)


def test_rejects_fake_extension(app):
    """.pdf extension but not actually a PDF → magic-byte sniff fails."""
    with app.app_context(), pytest.raises(ValidationError):
        validate_uploads(
            [_fs("masquerade.pdf", b"not a pdf")],
            user_id="u1",
            current_user_bytes=0,
        )


def test_accepts_valid_pdf(app):
    content = b"%PDF-1.4\n%%EOF"
    with app.app_context():
        validated = validate_uploads(
            [_fs("doc.pdf", content)], user_id="u1", current_user_bytes=0
        )
    assert len(validated) == 1
    assert validated[0][1].ext == "pdf"
    assert validated[0][1].size == len(content)


def test_quota_enforced(app):
    content = b"%PDF-1.4\n%%EOF"
    # PER_USER_STORAGE_MB=10MB in conftest; pretend 9.999MB already stored.
    already = 10 * 1024 * 1024 - 5
    with app.app_context(), pytest.raises(ValidationError):
        validate_uploads(
            [_fs("doc.pdf", content)], user_id="u1", current_user_bytes=already
        )


def test_sanitizes_path_traversal_filename(app):
    """secure_filename strips path segments — the saved name must not contain them."""
    with app.app_context():
        validated = validate_uploads(
            [_fs("../../etc/passwd.pdf", b"%PDF-1.4")],
            user_id="u1",
            current_user_bytes=0,
        )
    safe = validated[0][1].safe_name
    assert ".." not in safe
    assert "/" not in safe
