"""Retrieval metrics: Recall@K, MRR, hit-rate. A hit is a retrieved chunk whose
``source`` filename is in the question's expected ``source_docs`` — scored at the
document level (not chunk id, which shifts with chunk-size changes).
"""
from __future__ import annotations

from typing import Dict, Iterable, List


def _hit_ranks(retrieved_sources: List[str], expected: Iterable[str]) -> List[int]:
    """Return 1-indexed ranks at which an expected source first appears."""
    expected_set = set(expected)
    ranks: List[int] = []
    for i, src in enumerate(retrieved_sources, start=1):
        if src in expected_set:
            ranks.append(i)
    return ranks


def recall_at_k(retrieved_sources: List[str], expected: Iterable[str], *, k: int) -> float:
    expected_set = set(expected)
    if not expected_set:
        return 0.0
    top = set(retrieved_sources[:k])
    return len(top & expected_set) / len(expected_set)


def reciprocal_rank(retrieved_sources: List[str], expected: Iterable[str]) -> float:
    ranks = _hit_ranks(retrieved_sources, expected)
    return 1.0 / ranks[0] if ranks else 0.0


def hit_rate(retrieved_sources: List[str], expected: Iterable[str]) -> float:
    """Binary: 1 if any expected source appears anywhere in the top-K list."""
    return 1.0 if _hit_ranks(retrieved_sources, expected) else 0.0


def aggregate(per_row: List[Dict[str, float]]) -> Dict[str, float]:
    """Mean of each numeric field across rows."""
    if not per_row:
        return {}
    keys = {k for row in per_row for k, v in row.items() if isinstance(v, (int, float))}
    return {k: sum(float(r.get(k, 0.0)) for r in per_row) / len(per_row) for k in keys}
