"""Response & embedding cache with two layers: an exact SHA-256 key cache, and a
semantic cache that reuses an answer when a query embedding is within
``SEMANTIC_SIM_THRESHOLD`` of a cached one. Uses Redis when ``REDIS_URL`` is set,
otherwise a process-local LRU (single-process only).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

import numpy as np

from logging_config import get_logger

log = get_logger("cache")

DEFAULT_TTL = 60 * 60  # 1h
SEMANTIC_TTL = 60 * 30
SEMANTIC_SIM_THRESHOLD = 0.93


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: int) -> None: ...
    def zadd(self, zkey: str, member: str, score: float) -> None: ...
    def zrange(self, zkey: str, count: int) -> list[str]: ...


# ---------- In-memory fallback ----------------------------------------------------


class _InMemoryBackend:
    """Thread-safe bounded LRU with expiry. Good enough for single-process dev."""

    def __init__(self, maxsize: int = 2048) -> None:
        self._lock = threading.Lock()
        self._kv: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
        self._z: dict[str, list[tuple[float, str]]] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> str | None:
        with self._lock:
            hit = self._kv.get(key)
            if not hit:
                return None
            expires_at, val = hit
            if expires_at and expires_at < time.time():
                self._kv.pop(key, None)
                return None
            self._kv.move_to_end(key)
            return val

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._kv[key] = (time.time() + ttl, value)
            self._kv.move_to_end(key)
            while len(self._kv) > self._maxsize:
                self._kv.popitem(last=False)

    def zadd(self, zkey: str, member: str, score: float) -> None:
        with self._lock:
            arr = self._z.setdefault(zkey, [])
            arr.append((score, member))
            if len(arr) > 512:
                del arr[: len(arr) - 512]

    def zrange(self, zkey: str, count: int) -> list[str]:
        with self._lock:
            return [m for _, m in list(self._z.get(zkey, []))[-count:]]


# ---------- Redis backend ---------------------------------------------------------


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis  # type: ignore

        self._r = redis.Redis.from_url(url, decode_responses=True, socket_timeout=0.5)

    def get(self, key: str) -> str | None:
        try:
            return self._r.get(key)
        except Exception as e:
            log.warning("cache.redis.get_failed", error=str(e))
            return None

    def set(self, key: str, value: str, ttl: int) -> None:
        try:
            self._r.set(key, value, ex=ttl)
        except Exception as e:
            log.warning("cache.redis.set_failed", error=str(e))

    def zadd(self, zkey: str, member: str, score: float) -> None:
        try:
            self._r.zadd(zkey, {member: score})
            self._r.expire(zkey, SEMANTIC_TTL)
            self._r.zremrangebyrank(zkey, 0, -513)  # keep newest 512
        except Exception as e:
            log.warning("cache.redis.zadd_failed", error=str(e))

    def zrange(self, zkey: str, count: int) -> list[str]:
        try:
            return list(self._r.zrange(zkey, -count, -1) or [])
        except Exception as e:
            log.warning("cache.redis.zrange_failed", error=str(e))
            return []


# ---------- Public façade ---------------------------------------------------------


def _select_backend() -> CacheBackend:
    url = os.getenv("REDIS_URL")
    if not url:
        log.info("cache.backend", kind="memory")
        return _InMemoryBackend()
    try:
        backend = _RedisBackend(url)
        backend._r.ping()  # type: ignore[attr-defined]
        log.info("cache.backend", kind="redis", url=url)
        return backend
    except Exception as e:
        log.warning("cache.redis.unavailable_fallback_memory", error=str(e))
        return _InMemoryBackend()


_backend: CacheBackend | None = None


def _b() -> CacheBackend:
    global _backend
    if _backend is None:
        _backend = _select_backend()
    return _backend


def _key(parts: Iterable[Any]) -> str:
    raw = json.dumps(list(parts), sort_keys=True, default=str).encode()
    return "docai:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CachedAnswer:
    query: str
    answer: str
    sources: list[str]
    ts: float


def get_exact(user_id: str | None, query: str, top_k: int) -> CachedAnswer | None:
    from metrics import CACHE_HIT, CACHE_MISS  # late import: avoids boot-order coupling

    raw = _b().get(_key(["answer", user_id or "_anon", query.strip().lower(), top_k]))
    if not raw:
        CACHE_MISS.labels(layer="exact").inc()
        return None
    try:
        data = json.loads(raw)
        CACHE_HIT.labels(layer="exact").inc()
        return CachedAnswer(**data)
    except (ValueError, TypeError):
        CACHE_MISS.labels(layer="exact").inc()
        return None


def set_exact(
    user_id: str | None, query: str, top_k: int, answer: str, sources: list[str]
) -> None:
    payload = CachedAnswer(query=query, answer=answer, sources=sources, ts=time.time())
    _b().set(
        _key(["answer", user_id or "_anon", query.strip().lower(), top_k]),
        json.dumps(payload.__dict__),
        DEFAULT_TTL,
    )


# ---------- Semantic cache --------------------------------------------------------


def _vec_key(user_id: str | None) -> str:
    return _key(["sem-idx", user_id or "_anon"])


def _entry_key(user_id: str | None, h: str) -> str:
    return _key(["sem-entry", user_id or "_anon", h])


def _hash_vec(v: np.ndarray) -> str:
    return hashlib.sha1(v.astype("float32").tobytes(), usedforsecurity=False).hexdigest()


def semantic_get(
    user_id: str | None, query_embedding: np.ndarray
) -> CachedAnswer | None:
    """Return a cached answer whose query embedding is cosine-close to this one."""
    q = query_embedding.astype("float32").flatten()
    q /= np.linalg.norm(q) + 1e-12

    members = _b().zrange(_vec_key(user_id), count=64)
    if not members:
        return None

    best: tuple[float, CachedAnswer] | None = None
    for m in members:
        raw = _b().get(_entry_key(user_id, m))
        if not raw:
            continue
        try:
            entry = json.loads(raw)
            emb = np.array(entry["emb"], dtype="float32")
        except (ValueError, TypeError, KeyError):
            continue
        sim = float(np.dot(q, emb))
        if sim >= SEMANTIC_SIM_THRESHOLD and (best is None or sim > best[0]):
            best = (
                sim,
                CachedAnswer(
                    query=entry["query"],
                    answer=entry["answer"],
                    sources=entry.get("sources", []),
                    ts=entry.get("ts", 0.0),
                ),
            )
    from metrics import CACHE_HIT, CACHE_MISS

    if best:
        CACHE_HIT.labels(layer="semantic").inc()
        log.info("cache.semantic.hit", sim=round(best[0], 4))
        return best[1]
    CACHE_MISS.labels(layer="semantic").inc()
    return None


def semantic_set(
    user_id: str | None,
    query: str,
    query_embedding: np.ndarray,
    answer: str,
    sources: list[str],
) -> None:
    q = query_embedding.astype("float32").flatten()
    q /= np.linalg.norm(q) + 1e-12
    h = _hash_vec(q)
    entry = {
        "query": query,
        "answer": answer,
        "sources": sources,
        "emb": q.tolist(),
        "ts": time.time(),
    }
    _b().set(_entry_key(user_id, h), json.dumps(entry), SEMANTIC_TTL)
    _b().zadd(_vec_key(user_id), h, time.time())


def invalidate_user(user_id: str | None) -> None:
    """Best-effort invalidation on re-ingest; in-memory relies on TTL expiry."""
    # TODO: implement proper prefix deletion via Redis SCAN.
    log.info("cache.invalidate", user_id=user_id)
