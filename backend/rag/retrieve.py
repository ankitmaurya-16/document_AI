"""Retrieval pipeline: embed query, run vector + BM25 search, fuse with RRF,
then cross-encoder rerank. The vector backend (FAISS/Qdrant) is chosen in
``rag.vector_store``; this module is agnostic to it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from config import EMBEDDING_MODEL_NAME, SIMILARITY_THRESHOLD, TOP_K
from rag.hybrid import bm25_search, rrf_fuse
from rag.rerank import rerank
from rag.user_store import paths_for
from rag.vector_store import get_store

model = SentenceTransformer(EMBEDDING_MODEL_NAME)

_TOP_K_RETRIEVE = 50  # wide net for recall; narrowed by rerank
_DEFAULT_FINAL_TOP_K = TOP_K


def reload_index(user_id: Optional[str] = None) -> None:
    """Drop cached index handles (BM25) after an ingest/delete."""
    from rag.hybrid import reload_bm25

    if user_id is None:
        reload_bm25(None)
    else:
        reload_bm25(user_id)


def embed(texts: List[str]) -> np.ndarray:
    return model.encode(texts, normalize_embeddings=True).astype("float32")


def retrieve(
    query: str,
    *,
    user_id: Optional[str] = None,
    top_k: int = _DEFAULT_FINAL_TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
    query_embedding: np.ndarray | None = None,
) -> List[Dict]:
    namespace = paths_for(user_id).namespace
    store = get_store()

    q_emb = query_embedding if query_embedding is not None else embed([query])

    vector_hits = store.search(namespace, q_emb, _TOP_K_RETRIEVE, threshold)
    bm25_hits = bm25_search(query, user_id=user_id, metadata=None, top_k=_TOP_K_RETRIEVE)

    if bm25_hits:
        fused = rrf_fuse(vector_hits, bm25_hits, top_k=_TOP_K_RETRIEVE)
    else:
        fused = vector_hits

    if not fused:
        return []

    return rerank(query, fused, top_k=top_k)


def retrieve_top_chunks(
    query: str,
    top_k: int = _DEFAULT_FINAL_TOP_K,
    threshold: float = SIMILARITY_THRESHOLD,
    *,
    user_id: Optional[str] = None,
) -> List[Dict]:
    return retrieve(query, user_id=user_id, top_k=top_k, threshold=threshold)


def embed_query(query: str) -> np.ndarray:
    return embed([query])
