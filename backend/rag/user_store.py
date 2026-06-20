"""Per-user index paths and raw-file bookkeeping.

Each user gets ``data/index/users/{user_id}/`` (faiss.index + metadata.json);
callers with no user_id fall back to a shared ``_anon`` namespace.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# Base directory relative to the backend root.
_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_USERS_ROOT = _ROOT / "data" / "index" / "users"

_ID_OK = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


@dataclass(frozen=True)
class IndexPaths:
    namespace: str
    dir: str
    faiss_index: str
    metadata: str
    storage_meta: str  # tracks total bytes for quota enforcement

    def exists(self) -> bool:
        return os.path.exists(self.faiss_index) and os.path.exists(self.metadata)


def _safe_namespace(user_id: str | None) -> str:
    if not user_id:
        return "_anon"
    if not _ID_OK.match(str(user_id)):
        raise ValueError(f"Unsafe namespace id: {user_id!r}")
    return str(user_id)


def paths_for(user_id: str | None) -> IndexPaths:
    ns = _safe_namespace(user_id)
    base = _USERS_ROOT / ns
    base.mkdir(parents=True, exist_ok=True)
    (base / "raw").mkdir(parents=True, exist_ok=True)
    return IndexPaths(
        namespace=ns,
        dir=str(base),
        faiss_index=str(base / "faiss.index"),
        metadata=str(base / "metadata.json"),
        storage_meta=str(base / "storage.json"),
    )


def raw_dir_for(user_id: str | None) -> str:
    return str(Path(paths_for(user_id).dir) / "raw")


def save_raw_file(user_id: str | None, src_path: str, original_name: str) -> str:
    """Persist the tmp upload via the active storage backend; returns a canonical
    key (local path or ``s3://...`` URI)."""
    from storage import get_storage  # late import to avoid cycle
    return get_storage().save(_safe_namespace(user_id), src_path, original_name)


def remove_raw_file(key: str) -> bool:
    """Remove a previously-saved raw file. Accepts local paths or s3:// URIs."""
    from storage import get_storage
    return get_storage().remove(key)


def list_raw_files(user_id: str | None) -> list[str]:
    """List a user's raw-file keys (local paths or ``s3://...`` URIs)."""
    from storage import get_storage
    return [obj.key for obj in get_storage().list_keys(_safe_namespace(user_id))]


def wipe_namespace(user_id: str | None) -> None:
    paths = paths_for(user_id)
    if os.path.exists(paths.dir):
        shutil.rmtree(paths.dir)


def read_user_bytes(user_id: str | None) -> int:
    """Bytes stored for a user (sum over ingested files). 0 if unknown."""
    import json

    paths = paths_for(user_id)
    if not os.path.exists(paths.storage_meta):
        return 0
    try:
        with open(paths.storage_meta, "r", encoding="utf-8") as f:
            return int(json.load(f).get("bytes", 0))
    except (ValueError, OSError):
        return 0


def add_user_bytes(user_id: str | None, delta: int) -> int:
    import json

    paths = paths_for(user_id)
    current = read_user_bytes(user_id) + max(0, delta)
    with open(paths.storage_meta, "w", encoding="utf-8") as f:
        json.dump({"bytes": current}, f)
    return current
