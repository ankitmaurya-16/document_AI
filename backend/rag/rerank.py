"""Cross-encoder reranking for retrieved chunks.

Two-stage retrieval: a bi-encoder (FAISS + sentence-transformers) fetches a
wide candidate set with good recall, then a cross-encoder rescores the
(query, passage) pairs jointly for better precision.

Loaded lazily on first use to keep cold-start fast. ``RERANKER_MODEL``
overrides the model; ``RERANK_DISABLE=1`` short-circuits when the model
can't be downloaded.
"""
from __future__ import annotations

import os
from typing import List

from logging_config import get_logger

log = get_logger("rerank")

_MODEL_NAME = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
_DISABLED = os.getenv("RERANK_DISABLE") == "1"

_model = None


def _get_model():
    global _model
    if _model is not None or _DISABLED:
        return _model
    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        log.info("rerank.model.loading", model=_MODEL_NAME)
        _model = CrossEncoder(_MODEL_NAME, max_length=512)
    except Exception as e:
        log.warning("rerank.model.unavailable", error=str(e))
        _model = None
    return _model


def rerank(query: str, chunks: List[dict], *, top_k: int) -> List[dict]:
    """Return the top ``top_k`` chunks reordered by cross-encoder relevance.

    Falls back to the input order (truncated to top_k) if the model is not
    available or raises.
    """
    if not chunks:
        return []

    model = _get_model()
    if model is None:
        return chunks[:top_k]

    pairs = [(query, c.get("text", "")) for c in chunks]
    try:
        scores = model.predict(pairs, show_progress_bar=False)
    except Exception as e:
        log.warning("rerank.predict_failed", error=str(e))
        return chunks[:top_k]

    for c, s in zip(chunks, scores):
        c["rerank_score"] = float(s)
    return sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)[:top_k]
