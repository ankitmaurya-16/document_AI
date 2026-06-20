"""Raw file storage backend: local disk by default, or S3/MinIO when
``S3_ENDPOINT`` / ``S3_BUCKET`` is set (boto3 talks to both). Exposes
save / remove / list_keys / fetch_to_local / signed_url, keyed by user namespace.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

from logging_config import get_logger
from resilience import with_retry

log = get_logger("storage")

try:
    from botocore.exceptions import (  # type: ignore
        ConnectionError as _BotoConn,
        EndpointConnectionError,
        ReadTimeoutError,
    )
    _S3_RETRY_TYPES = (_BotoConn, EndpointConnectionError, ReadTimeoutError)
except ImportError:
    _S3_RETRY_TYPES = (ConnectionError,)


@with_retry("s3", exception_types=_S3_RETRY_TYPES)
def _s3_call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@dataclass
class StoredObject:
    key: str
    name: str
    size: int
    modified: float  # unix epoch seconds


class RawStorage(Protocol):
    backend: str

    def save(self, user_id: str, src_path: str, original_name: str) -> str: ...
    def remove(self, key: str) -> bool: ...
    def list_keys(self, user_id: str) -> List[StoredObject]: ...
    def fetch_to_local(self, key: str, dest_dir: Optional[str] = None) -> str: ...
    def signed_url(self, key: str, ttl: int = 300) -> Optional[str]: ...


# ---------------------------------------------------------------- local backend


class _LocalStorage:
    backend = "local"

    def __init__(self) -> None:
        from rag.user_store import raw_dir_for  # late import to avoid cycle
        self._raw_dir_for = raw_dir_for

    def _user_dir(self, user_id: str) -> Path:
        d = Path(self._raw_dir_for(user_id))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, user_id: str, src_path: str, original_name: str) -> str:
        target_dir = self._user_dir(user_id)
        dest = target_dir / original_name
        stem, ext = os.path.splitext(original_name)
        n = 1
        while dest.exists():
            dest = target_dir / f"{stem} ({n}){ext}"
            n += 1
        shutil.copy2(src_path, dest)
        return str(dest)

    def remove(self, key: str) -> bool:
        try:
            os.remove(key)
            return True
        except OSError:
            return False

    def list_keys(self, user_id: str) -> List[StoredObject]:
        d = self._user_dir(user_id)
        out: list[StoredObject] = []
        for p in d.iterdir():
            if p.is_file():
                stat = p.stat()
                out.append(StoredObject(key=str(p), name=p.name, size=stat.st_size, modified=stat.st_mtime))
        return out

    def fetch_to_local(self, key: str, dest_dir: Optional[str] = None) -> str:
        if dest_dir is None:
            return key  # already local
        dest = Path(dest_dir) / Path(key).name
        shutil.copy2(key, dest)
        return str(dest)

    def signed_url(self, key: str, ttl: int = 300) -> Optional[str]:
        return None  # local files aren't web-accessible


# ------------------------------------------------------------------ S3 backend


class _S3Storage:
    backend = "s3"

    def __init__(self, *, bucket: str, endpoint: Optional[str], region: Optional[str],
                 access_key: Optional[str], secret_key: Optional[str]) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self._bucket)
                log.info("s3.bucket_created", bucket=self._bucket)
            except Exception as e:  # already exists or no perms
                log.warning("s3.bucket_ensure_failed", bucket=self._bucket, error=str(e))

    def _object_key(self, user_id: str, name: str) -> str:
        return f"{user_id}/{name}"

    def _uri(self, object_key: str) -> str:
        return f"s3://{self._bucket}/{object_key}"

    @staticmethod
    def _parse_uri(key: str) -> tuple[str, str]:
        assert key.startswith("s3://"), f"Not an s3:// uri: {key}"
        rest = key[len("s3://"):]
        bucket, _, object_key = rest.partition("/")
        return bucket, object_key

    def save(self, user_id: str, src_path: str, original_name: str) -> str:
        # Avoid collisions with a numeric suffix, like the local backend.
        base = original_name
        stem, ext = os.path.splitext(original_name)
        n = 1
        while self._object_exists(self._object_key(user_id, base)):
            base = f"{stem} ({n}){ext}"
            n += 1
        obj_key = self._object_key(user_id, base)
        _s3_call(self._client.upload_file, src_path, self._bucket, obj_key)
        return self._uri(obj_key)

    def _object_exists(self, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except Exception:
            return False

    def remove(self, key: str) -> bool:
        bucket, object_key = self._parse_uri(key)
        try:
            _s3_call(self._client.delete_object, Bucket=bucket, Key=object_key)
            return True
        except Exception as e:
            log.warning("s3.delete_failed", key=key, error=str(e))
            return False

    def list_keys(self, user_id: str) -> List[StoredObject]:
        out: list[StoredObject] = []
        prefix = f"{user_id}/"
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    name = obj["Key"][len(prefix):]
                    out.append(StoredObject(
                        key=self._uri(obj["Key"]),
                        name=name,
                        size=obj["Size"],
                        modified=obj["LastModified"].timestamp(),
                    ))
        except Exception as e:
            log.warning("s3.list_failed", user_id=user_id, error=str(e))
        return out

    def fetch_to_local(self, key: str, dest_dir: Optional[str] = None) -> str:
        bucket, object_key = self._parse_uri(key)
        if dest_dir is None:
            dest_dir = tempfile.mkdtemp(prefix="docai_s3_")
        dest = Path(dest_dir) / Path(object_key).name
        _s3_call(self._client.download_file, bucket, object_key, str(dest))
        return str(dest)

    def signed_url(self, key: str, ttl: int = 300) -> Optional[str]:
        bucket, object_key = self._parse_uri(key)
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=ttl,
            )
        except Exception as e:
            log.warning("s3.signed_url_failed", error=str(e))
            return None


# ------------------------------------------------------------------- factory


_lock = threading.Lock()
_storage: RawStorage | None = None


def _build_storage() -> RawStorage:
    bucket = (os.getenv("S3_BUCKET") or "").strip()
    endpoint = (os.getenv("S3_ENDPOINT") or "").strip() or None
    use_s3 = bool(bucket) and (endpoint or os.getenv("AWS_ACCESS_KEY_ID"))
    if use_s3:
        log.info("storage.selected", backend="s3", bucket=bucket, endpoint=endpoint or "aws")
        return _S3Storage(
            bucket=bucket,
            endpoint=endpoint,
            region=os.getenv("AWS_REGION") or os.getenv("S3_REGION") or "us-east-1",
            access_key=os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("S3_ACCESS_KEY"),
            secret_key=os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("S3_SECRET_KEY"),
        )
    log.info("storage.selected", backend="local")
    return _LocalStorage()


def get_storage() -> RawStorage:
    global _storage
    if _storage is None:
        with _lock:
            if _storage is None:
                _storage = _build_storage()
    return _storage


def reset_storage_for_tests() -> None:
    global _storage
    with _lock:
        _storage = None


# ------------------------------------------------------------- helper for ingest


def materialize_keys_to_dir(keys: list[str], dest_dir: str) -> list[str]:
    """Download/copy stored keys into ``dest_dir`` and return local paths (so the
    ingestion code, which only handles local paths, doesn't care about S3)."""
    storage = get_storage()
    os.makedirs(dest_dir, exist_ok=True)
    out: list[str] = []
    for key in keys:
        try:
            out.append(storage.fetch_to_local(key, dest_dir=dest_dir))
        except Exception as e:
            log.warning("storage.materialize_failed", key=key, error=str(e))
    return out
