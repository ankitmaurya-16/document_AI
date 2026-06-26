"""Unit tests for BM25 build + RRF fusion.

RRF is pure math over ranked lists, so these tests don't need a real
index. BM25 build/search is tested via a temp-directory roundtrip.
"""
from __future__ import annotations

import os

import pytest

from rag.hybrid import _tokenize, rrf_fuse


def test_tokenize_lowercases_and_drops_punctuation():
    assert _tokenize("Hello, World! 42.") == ["hello", "world", "42"]


def test_tokenize_handles_empty_and_none_safely():
    assert _tokenize("") == []
    assert _tokenize(None) == []  # type: ignore[arg-type]


def test_rrf_agrees_with_unanimous_ranking():
    # Both retrievers rank A > B > C → RRF must preserve that order.
    vec = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    lex = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    fused = rrf_fuse(vec, lex, top_k=3)
    assert [r["chunk_id"] for r in fused] == ["a", "b", "c"]


def test_rrf_rewards_appearing_in_both_lists():
    # "b" appears in both lists; "a" only in vector; "c" only in lex.
    # With default k=60, b's fused score (1/61 + 1/61) beats the others.
    vec = [{"chunk_id": "a"}, {"chunk_id": "b"}]
    lex = [{"chunk_id": "c"}, {"chunk_id": "b"}]
    fused = rrf_fuse(vec, lex, top_k=3)
    assert fused[0]["chunk_id"] == "b"


def test_rrf_top_k_truncation():
    vec = [{"chunk_id": f"v{i}"} for i in range(10)]
    lex = [{"chunk_id": f"l{i}"} for i in range(10)]
    assert len(rrf_fuse(vec, lex, top_k=5)) == 5


def test_rrf_empty_lists_return_empty():
    assert rrf_fuse([], [], top_k=5) == []


def test_bm25_build_and_search_roundtrip(monkeypatch, tmp_path):
    """End-to-end over a per-test user_id so the on-disk artefact is isolated."""
    pytest.importorskip("rank_bm25")

    from rag import hybrid, user_store

    # Point user_store at a temp dir so we don't touch real user data.
    monkeypatch.setattr(user_store, "_USERS_ROOT", tmp_path)
    # hybrid imports paths_for at module level, so patch its reference too.
    monkeypatch.setattr(hybrid, "paths_for", user_store.paths_for)

    metadata = [
        {"chunk_id": "c1", "source": "a.txt", "text": "the quick brown fox"},
        {"chunk_id": "c2", "source": "b.txt", "text": "lazy dogs sleep often"},
        {"chunk_id": "c3", "source": "a.txt", "text": "brown fox jumps over"},
    ]
    hybrid.build_bm25(user_id="u1", metadata=metadata)
    hybrid.reload_bm25("u1")  # drop cache so search re-reads from disk

    hits = hybrid.bm25_search("brown fox", user_id="u1", metadata=None, top_k=2)
    assert len(hits) <= 2
    assert any(h["chunk_id"] == "c1" for h in hits) or any(h["chunk_id"] == "c3" for h in hits)


def test_bm25_search_returns_empty_when_no_index(monkeypatch, tmp_path):
    from rag import hybrid, user_store

    monkeypatch.setattr(user_store, "_USERS_ROOT", tmp_path)
    monkeypatch.setattr(hybrid, "paths_for", user_store.paths_for)
    # Reset BM25 cache for this namespace.
    monkeypatch.setattr(hybrid, "_bm25_cache", {}, raising=False)
    # No build_bm25 call → no on-disk artefact → search must return [].
    assert hybrid.bm25_search("anything", user_id="missing", metadata=None, top_k=5) == []


# Sanity: user_store must create raw/ alongside the index dir.
def test_user_store_paths_for_creates_dirs(monkeypatch, tmp_path):
    from rag import user_store

    monkeypatch.setattr(user_store, "_USERS_ROOT", tmp_path)
    paths = user_store.paths_for("alice")
    assert os.path.isdir(paths.dir)
    assert os.path.isdir(os.path.join(paths.dir, "raw"))
    assert paths.namespace == "alice"
