"""Vector store abstraction over FAISS (local) and Qdrant.

Backend is Qdrant when ``VECTOR_BACKEND=qdrant`` or ``QDRANT_URL`` is set, else
FAISS on local disk. The namespace-keyed interface (upsert/search/delete/exists)
hides the backend; namespace is the per-user id (``_anon`` shared).
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from typing import Dict, List, Optional, Protocol

import numpy as np

from logging_config import get_logger
from rag.user_store import paths_for
from resilience import with_retry

log = get_logger("rag.vector_store")

# Qdrant raises subclasses of UnexpectedResponse / ResponseHandlingException
# from qdrant_client.http on transient failures. Catch broadly — caller-side
# decoration only retries network-shaped errors via tenacity's exception filter.
try:
    from qdrant_client.http.exceptions import (  # type: ignore
        ResponseHandlingException,
        UnexpectedResponse,
    )
    _QDRANT_RETRY_TYPES = (ResponseHandlingException, UnexpectedResponse, ConnectionError)
except ImportError:
    _QDRANT_RETRY_TYPES = (ConnectionError,)


@with_retry("qdrant", exception_types=_QDRANT_RETRY_TYPES)
def _qdrant_call(fn, *args, **kwargs):
    return fn(*args, **kwargs)


class VectorStore(Protocol):
    backend: str

    def upsert(self, namespace: str, vectors: np.ndarray, metadata: List[Dict]) -> None: ...
    def search(
        self, namespace: str, query_vec: np.ndarray, top_k: int, threshold: float
    ) -> List[Dict]: ...
    def delete(self, namespace: str) -> None: ...
    def exists(self, namespace: str) -> bool: ...
    def get_metadata(self, namespace: str) -> List[Dict]: ...


# ---------------------------------------------------------------- FAISS backend


class _FaissStore:
    backend = "faiss"

    def __init__(self) -> None:
        import faiss  # local import; tests stub this out
        self._faiss = faiss
        self._cache: dict[str, tuple] = {}  # namespace → (index, metadata)
        self._lock = threading.Lock()

    def _load(self, namespace: str):
        with self._lock:
            hit = self._cache.get(namespace)
            if hit is not None:
                return hit
            paths = paths_for(None if namespace == "_anon" else namespace)
            if not paths.exists():
                return None
            index = self._faiss.read_index(paths.faiss_index)
            try:
                index.hnsw.efSearch = 64
            except AttributeError:
                pass
            with open(paths.metadata, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            self._cache[namespace] = (index, metadata)
            return self._cache[namespace]

    def upsert(self, namespace: str, vectors: np.ndarray, metadata: List[Dict]) -> None:
        paths = paths_for(None if namespace == "_anon" else namespace)
        # Reset namespace dir (destructive within user's own namespace only).
        if os.path.exists(paths.dir):
            # Preserve raw/ — only the index files get rewritten.
            for entry in os.listdir(paths.dir):
                full = os.path.join(paths.dir, entry)
                if entry == "raw":
                    continue
                if os.path.isfile(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
        os.makedirs(paths.dir, exist_ok=True)

        dim = vectors.shape[1]
        index = self._faiss.IndexHNSWFlat(dim, 32)
        index.hnsw.efConstruction = 200
        index.metric_type = self._faiss.METRIC_INNER_PRODUCT
        index.train(vectors)
        index.add(vectors)
        self._faiss.write_index(index, paths.faiss_index)
        with open(paths.metadata, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        with self._lock:
            self._cache.pop(namespace, None)

    def search(
        self, namespace: str, query_vec: np.ndarray, top_k: int, threshold: float
    ) -> List[Dict]:
        loaded = self._load(namespace)
        if loaded is None:
            return []
        index, metadata = loaded
        scores, indices = index.search(query_vec, top_k)
        out: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(metadata):
                continue
            if score < threshold:
                continue
            chunk = metadata[idx]
            out.append({
                "chunk_id": chunk["chunk_id"],
                "source": chunk["source"],
                "text": chunk["text"],
                "score": float(score),
            })
        return out

    def delete(self, namespace: str) -> None:
        paths = paths_for(None if namespace == "_anon" else namespace)
        if os.path.exists(paths.faiss_index):
            os.remove(paths.faiss_index)
        if os.path.exists(paths.metadata):
            os.remove(paths.metadata)
        with self._lock:
            self._cache.pop(namespace, None)

    def exists(self, namespace: str) -> bool:
        paths = paths_for(None if namespace == "_anon" else namespace)
        return paths.exists()

    def get_metadata(self, namespace: str) -> List[Dict]:
        loaded = self._load(namespace)
        if loaded is None:
            return []
        return loaded[1]


# --------------------------------------------------------------- Qdrant backend


class _QdrantStore:
    backend = "qdrant"
    COLLECTION = "docai_chunks"

    def __init__(self, url: str, api_key: Optional[str] = None) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm

        self._client = QdrantClient(url=url, api_key=api_key)
        self._models = qm
        self._lock = threading.Lock()
        self._ensured_dim: Optional[int] = None

    def _ensure_collection(self, dim: int) -> None:
        with self._lock:
            if self._ensured_dim == dim:
                return
            qm = self._models
            collections = {c.name for c in self._client.get_collections().collections}
            if self.COLLECTION not in collections:
                self._client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
                )
                # Index user_id payload for cheap filter lookups.
                self._client.create_payload_index(
                    collection_name=self.COLLECTION,
                    field_name="user_id",
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
                log.info("qdrant.collection_created", name=self.COLLECTION, dim=dim)
            self._ensured_dim = dim

    def _user_filter(self, namespace: str):
        qm = self._models
        return qm.Filter(must=[qm.FieldCondition(key="user_id", match=qm.MatchValue(value=namespace))])

    def upsert(self, namespace: str, vectors: np.ndarray, metadata: List[Dict]) -> None:
        self._ensure_collection(vectors.shape[1])
        # Replace this user's vectors atomically: delete-by-filter then insert.
        _qdrant_call(
            self._client.delete,
            collection_name=self.COLLECTION,
            points_selector=self._models.FilterSelector(filter=self._user_filter(namespace)),
        )
        points = []
        for i, (vec, meta) in enumerate(zip(vectors, metadata)):
            points.append(
                self._models.PointStruct(
                    id=f"{namespace}:{meta['chunk_id']}",
                    vector=vec.tolist(),
                    payload={
                        "user_id": namespace,
                        "chunk_id": meta["chunk_id"],
                        "source": meta["source"],
                        "text": meta["text"],
                    },
                )
            )
        # Batch in chunks of 256 to keep individual requests bounded.
        for start in range(0, len(points), 256):
            _qdrant_call(
                self._client.upsert,
                collection_name=self.COLLECTION,
                points=points[start:start + 256],
            )

    def search(
        self, namespace: str, query_vec: np.ndarray, top_k: int, threshold: float
    ) -> List[Dict]:
        try:
            hits = _qdrant_call(
                self._client.search,
                collection_name=self.COLLECTION,
                query_vector=query_vec[0].tolist(),
                query_filter=self._user_filter(namespace),
                limit=top_k,
                score_threshold=threshold,
            )
        except Exception as e:  # collection might not exist yet
            log.warning("qdrant.search_failed", error=str(e))
            return []
        out: list[dict] = []
        for h in hits:
            payload = h.payload or {}
            out.append({
                "chunk_id": payload.get("chunk_id"),
                "source": payload.get("source"),
                "text": payload.get("text"),
                "score": float(h.score),
            })
        return out

    def delete(self, namespace: str) -> None:
        try:
            self._client.delete(
                collection_name=self.COLLECTION,
                points_selector=self._models.FilterSelector(filter=self._user_filter(namespace)),
            )
        except Exception as e:
            log.warning("qdrant.delete_failed", error=str(e))

    def exists(self, namespace: str) -> bool:
        try:
            res, _ = self._client.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=self._user_filter(namespace),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            return len(res) > 0
        except Exception:
            return False

    def get_metadata(self, namespace: str) -> List[Dict]:
        out: list[dict] = []
        try:
            offset = None
            while True:
                res, next_offset = self._client.scroll(
                    collection_name=self.COLLECTION,
                    scroll_filter=self._user_filter(namespace),
                    limit=512,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for point in res:
                    p = point.payload or {}
                    out.append({
                        "chunk_id": p.get("chunk_id"),
                        "source": p.get("source"),
                        "text": p.get("text"),
                    })
                if next_offset is None:
                    break
                offset = next_offset
        except Exception as e:
            log.warning("qdrant.scroll_failed", error=str(e))
        return out


# ----------------------------------------------------------------- factory


_store_lock = threading.Lock()
_store: VectorStore | None = None


def _build_store() -> VectorStore:
    backend = (os.getenv("VECTOR_BACKEND") or "").lower().strip()
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    if backend == "qdrant" or (not backend and qdrant_url):
        if not qdrant_url:
            raise RuntimeError("VECTOR_BACKEND=qdrant requires QDRANT_URL to be set.")
        log.info("vector_store.selected", backend="qdrant", url=qdrant_url)
        return _QdrantStore(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None)
    log.info("vector_store.selected", backend="faiss")
    return _FaissStore()


def get_store() -> VectorStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = _build_store()
    return _store


def reset_store_for_tests() -> None:
    """Drop the cached store. Tests use this after monkeypatching env."""
    global _store
    with _store_lock:
        _store = None
