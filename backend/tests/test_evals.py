"""Unit tests for the eval harness: metric math and golden-dataset validity. The
full ingest/retrieve pipeline runs under the `evals-smoke` CI job instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.metrics import aggregate, hit_rate, recall_at_k, reciprocal_rank


_DATASET = Path(__file__).resolve().parents[1] / "evals" / "dataset" / "golden.jsonl"
_DOCS_DIR = Path(__file__).resolve().parents[1] / "evals" / "dataset" / "docs"


# --- Metrics ---------------------------------------------------------------


def test_recall_at_1_perfect_hit():
    assert recall_at_k(["a.txt", "b.txt", "c.txt"], ["a.txt"], k=1) == 1.0


def test_recall_at_1_miss():
    assert recall_at_k(["b.txt", "a.txt"], ["a.txt"], k=1) == 0.0


def test_recall_at_5_multiple_expected():
    retrieved = ["a.txt", "x.txt", "b.txt", "y.txt", "z.txt"]
    # expected = {a, b}; both in top-5 → 2/2
    assert recall_at_k(retrieved, ["a.txt", "b.txt"], k=5) == 1.0


def test_reciprocal_rank_second_position():
    assert reciprocal_rank(["x", "a", "y"], ["a"]) == pytest.approx(0.5)


def test_reciprocal_rank_no_hit():
    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0


def test_hit_rate_binary():
    assert hit_rate(["x", "a"], ["a"]) == 1.0
    assert hit_rate(["x", "y"], ["a"]) == 0.0


def test_aggregate_means_numeric_fields():
    agg = aggregate([
        {"recall_at_5": 1.0, "mrr": 1.0},
        {"recall_at_5": 0.0, "mrr": 0.5},
    ])
    assert agg["recall_at_5"] == pytest.approx(0.5)
    assert agg["mrr"] == pytest.approx(0.75)


# --- Dataset validity -----------------------------------------------------


def _load_rows() -> list[dict]:
    rows: list[dict] = []
    with open(_DATASET, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def test_dataset_has_thirty_rows():
    assert len(_load_rows()) == 30


def test_dataset_ids_are_unique():
    ids = [r["id"] for r in _load_rows()]
    assert len(ids) == len(set(ids))


def test_dataset_required_fields():
    for row in _load_rows():
        assert set(row.keys()) >= {"id", "question", "expected_answer", "source_docs"}
        assert isinstance(row["source_docs"], list) and row["source_docs"]
        assert row["question"].strip() and row["expected_answer"].strip()


def test_dataset_sources_exist_on_disk():
    existing = {p.name for p in _DOCS_DIR.iterdir() if p.is_file()}
    for row in _load_rows():
        for src in row["source_docs"]:
            assert src in existing, f"{row['id']} references missing {src}"
