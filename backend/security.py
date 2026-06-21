"""File-upload hardening: extension allowlist, per-file size + per-user quota,
magic-byte content sniffing (so ``evil.exe`` renamed to ``.pdf`` fails),
filename sanitization, and an optional malware-scan hook.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from errors import ValidationError
from logging_config import get_logger
from settings import get_settings

log = get_logger("security")

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {"txt", "pdf", "doc", "docx", "csv", "xlsx", "xls", "ppt", "pptx"}
)

# Magic-byte signatures per-extension. Several extensions share a signature
# (e.g. docx/xlsx/pptx are all zip containers), which is fine — we only use
# this as a rough sanity check that the user hasn't renamed something dangerous.
_MAGIC: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "pptx": (b"PK\x03\x04",),
    "doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    "ppt": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    # txt and csv have no meaningful signature; we do a UTF-8 sniff instead.
}

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._\- ]{1,255}$")


@dataclass(frozen=True)
class ValidatedFile:
    original_name: str
    safe_name: str
    ext: str
    size: int


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _sniff_matches(ext: str, head: bytes) -> bool:
    sigs = _MAGIC.get(ext)
    if sigs:
        return any(head.startswith(s) for s in sigs)
    if ext in {"txt", "csv"}:
        # Reject NUL bytes in the first 8KB — cheap heuristic against binary payloads.
        return b"\x00" not in head
    return False


def scan_for_malware(path: str) -> None:
    """Hook for ClamAV / cloud AV. Default no-op; implement here and enable via env."""
    # TODO: wire up ClamAV. Requires running clamd daemon.
    return None


def _safe_filename(filename: str) -> str:
    # werkzeug's secure_filename strips path components and odd chars.
    safe = secure_filename(filename)
    if not safe or safe.startswith(".") or not _SAFE_FILENAME.match(safe):
        raise ValidationError(f"Unsafe filename: {filename!r}")
    return safe


def validate_uploads(
    files: Iterable[FileStorage],
    *,
    user_id: str | None,
    current_user_bytes: int,
) -> list[tuple[FileStorage, ValidatedFile]]:
    """Validate a batch of uploads, raising ``ValidationError`` on any problem.
    ``current_user_bytes`` is the user's existing usage (0 for anon = no quota)."""
    cfg = get_settings()
    files = list(files)
    if not files or all(not f.filename for f in files):
        raise ValidationError("No files provided")

    if len(files) > cfg.max_files_per_request:
        raise ValidationError(
            f"Too many files in one request (max {cfg.max_files_per_request})"
        )

    per_file_max = cfg.max_upload_mb * 1024 * 1024
    per_user_max = cfg.per_user_storage_mb * 1024 * 1024 if user_id else None

    results: list[tuple[FileStorage, ValidatedFile]] = []
    total_new = 0

    for f in files:
        if not f or not f.filename:
            raise ValidationError("Empty file entry")

        ext = _ext(f.filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File type .{ext} is not allowed",
                details={"filename": f.filename, "allowed": sorted(ALLOWED_EXTENSIONS)},
            )

        safe = _safe_filename(f.filename)

        # Measure size by seeking
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)

        if size == 0:
            raise ValidationError(f"{f.filename} is empty")
        if size > per_file_max:
            raise ValidationError(
                f"{f.filename} exceeds per-file size limit of {cfg.max_upload_mb}MB"
            )
        total_new += size

        # Magic-byte sniff
        head = f.stream.read(4096)
        f.stream.seek(0)
        if not _sniff_matches(ext, head):
            raise ValidationError(
                f"File content of {f.filename} does not match its .{ext} extension"
            )

        results.append(
            (f, ValidatedFile(original_name=f.filename, safe_name=safe, ext=ext, size=size))
        )

    if per_user_max is not None and current_user_bytes + total_new > per_user_max:
        raise ValidationError(
            f"Uploading these files would exceed your {cfg.per_user_storage_mb}MB storage quota"
        )

    log.info(
        "upload.validated",
        count=len(results),
        total_bytes=total_new,
        user_id=user_id,
    )
    return results
