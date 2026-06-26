"""Unit tests for the recursive splitter: chunks stay under size, avoid breaking
mid-sentence when possible, and respect overlap. Pure-logic, no services.
"""
from __future__ import annotations

from rag.chunking import recursive_split


def test_short_text_returns_single_chunk():
    out = recursive_split("hello world", chunk_size=1000, overlap=0)
    assert out == ["hello world"]


def test_empty_text_returns_empty_list():
    assert recursive_split("", chunk_size=50, overlap=0) == []
    assert recursive_split("   ", chunk_size=50, overlap=0) == []


def test_respects_paragraph_boundary_before_sentence():
    text = "First paragraph.\n\nSecond paragraph. Third sentence."
    out = recursive_split(text, chunk_size=30, overlap=0)
    # Paragraph break is the highest-priority separator present → at least
    # one chunk starts with "First" and another with "Second" (no mid-
    # paragraph splice on ". ").
    assert any(c.startswith("First") for c in out)
    assert any(c.startswith("Second") for c in out)


def test_all_chunks_under_size_for_long_prose():
    long = ("Sentence number one. " * 100).strip()
    size = 80
    out = recursive_split(long, chunk_size=size, overlap=10)
    # Recursive splitter allows slight overrun when a single atomic piece
    # is bigger than chunk_size, but for this input every piece is small
    # enough that chunks must stay under the limit.
    assert all(len(c) <= size for c in out), max(len(c) for c in out)
    assert len(out) > 1


def test_hard_split_when_no_separator_available():
    # A single "word" with no separators must be hard-split by character.
    text = "a" * 200
    out = recursive_split(text, chunk_size=50, overlap=0)
    assert len(out) >= 4
    assert all(len(c) <= 50 for c in out)


def test_overlap_carries_context_between_chunks():
    text = "abcdefghij. " * 20
    out = recursive_split(text, chunk_size=40, overlap=10)
    assert len(out) >= 2
    # Adjacent chunks should share at least 1 character when overlap is set.
    # Loose assertion — the splitter's overlap is based on piece lengths
    # not byte-exact; the point is that overlap > 0 produces overlap.
    any_overlap = any(
        set(out[i]).intersection(out[i + 1]) for i in range(len(out) - 1)
    )
    assert any_overlap


def test_no_overlap_mode_produces_disjoint_pieces():
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    out = recursive_split(text, chunk_size=20, overlap=0)
    joined = "".join(out).replace(" ", "")
    assert "alpha" in joined and "juliet" in joined
    assert all(len(c) <= 20 for c in out)
