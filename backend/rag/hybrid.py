"""BM25 lexical index + Reciprocal Rank Fusion with vector results.

Pure vector search misses exact keyword matches; BM25 catches them. We keep
one BM25 index per user namespace and fuse its ranking with the vector
ranking via RRF:

    score(d) = Σ_r 1 / (k + rank_r(d))

with k=60.
"""
from __future__ import annotations

import os
import pickle
import re
from typing import Dict, List, Optional

from logging_config import get_logger
from rag.user_store import paths_for

log = get_logger("hybrid")

_RRF_K = 60

_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _bm25_path(user_id: str | None) -> str:
    return os.path.join(paths_for(user_id).dir, "bm25.pkl")


def build_bm25(user_id: str | None, metadata: List[Dict]) -> None:
    """Persist a BM25Okapi index for this user's corpus. Call at end of ingest."""
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
    except ImportError:
        log.warning("bm25.dependency_missing", hint="pip install rank-bm25")
        return

    corpus = [_tokenize(m.get("text", "")) for m in metadata]
    if not corpus:
        return
    bm25 = BM25Okapi(corpus)
    with open(_bm25_path(user_id), "wb") as f:
        pickle.dump(
            {
                "bm25": bm25,
                "ids": [m["chunk_id"] for m in metadata],
                # Snapshot source/text per chunk so bm25_search doesn't need to
                # reload the vector store's metadata (Qdrant doesn't keep one).
                "meta": [{"source": m["source"], "text": m["text"]} for m in metadata],
            },
            f,
        )
    log.info("bm25.built", docs=len(corpus), user_id=user_id)


_bm25_cache: dict[str, dict] = {}


def _load_bm25(user_id: str | None) -> Optional[dict]:
    paths = paths_for(user_id)
    ns = paths.namespace
    if ns in _bm25_cache:
        return _bm25_cache[ns]
    p = _bm25_path(user_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            loaded = pickle.load(f)  # nosec B301 - file is written by this process under a per-user namespace
        _bm25_cache[ns] = loaded
        return loaded
    except Exception as e:
        log.warning("bm25.load_failed", error=str(e))
        return None


def reload_bm25(user_id: str | None) -> None:
    _bm25_cache.pop(paths_for(user_id).namespace, None)


def rrf_fuse(vector_results: List[dict], bm25_results: List[dict], *, top_k: int) -> List[dict]:
    """Fuse two ranked lists by chunk_id using RRF. Returns merged & sorted list."""
    by_id: dict[str, dict] = {}
    scores: dict[str, float] = {}

    for rank, r in enumerate(vector_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)
        by_id.setdefault(cid, dict(r))

    for rank, r in enumerate(bm25_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank + 1)
        by_id.setdefault(cid, dict(r))

    merged = []
    for cid, merged_score in scores.items():
        entry = dict(by_id[cid])
        entry["fused_score"] = merged_score
        merged.append(entry)
    merged.sort(key=lambda x: x["fused_score"], reverse=True)
    return merged[:top_k]


def bm25_search(
    query: str,
    *,
    user_id: str | None,
    metadata: List[Dict] | None = None,
    top_k: int,
) -> List[dict]:
    loaded = _load_bm25(user_id)
    if not loaded:
        return []
    try:
        scores = loaded["bm25"].get_scores(_tokenize(query))
    except Exception as e:
        log.warning("bm25.score_failed", error=str(e))
        return []

    ids = loaded["ids"]
    snap = loaded.get("meta") or []
    # Prefer the in-pickle snapshot (works for Qdrant + FAISS); fall back to the
    # caller-supplied metadata for older indexes built before the snapshot field.
    by_id_external = {m["chunk_id"]: m for m in (metadata or [])}

    out: list[dict] = []
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    for idx in ranked:
        if idx >= len(ids):
            continue
        cid = ids[idx]
        m: dict | None
        if idx < len(snap):
            m = snap[idx]
        else:
            m = by_id_external.get(cid)
        if not m:
            continue
        out.append({
            "chunk_id": cid,
            "source": m["source"],
            "text": m["text"],
            "score": float(scores[idx]),
        })
    return out
