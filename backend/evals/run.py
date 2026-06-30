"""RAG evaluation runner.

    python -m evals.run                            # retrieval-only over all rows
    python -m evals.run --judge                    # + LLM-as-judge (needs OPENAI_API_KEY)
    python -m evals.run --smoke --baseline-check   # CI smoke, fails on Recall@5 drop

Writes a JSON record and a Markdown summary under ``evals/results/``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# `rag/ingest.py` does `from config import ...`, which resolves when
# ``backend/rag`` is on sys.path (as the tests and gunicorn setup already
# ensure). Replicate that here so the runner works as `python -m evals.run`.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND / "rag") not in sys.path:
    sys.path.insert(0, str(_BACKEND / "rag"))

from evals.metrics import aggregate, hit_rate, recall_at_k, reciprocal_rank  # noqa: E402
from logging_config import get_logger  # noqa: E402

log = get_logger("evals.run")

_EVALS_DIR = Path(__file__).resolve().parent
_DATASET = _EVALS_DIR / "dataset" / "golden.jsonl"
_DOCS_DIR = _EVALS_DIR / "dataset" / "docs"
_RESULTS_DIR = _EVALS_DIR / "results"
_BASELINE_PATH = _EVALS_DIR / "baseline.json"

_EVAL_NAMESPACE = "_eval"
_TOP_K = 10
# Recall@5 is our headline metric; tolerance absorbs run-to-run noise from
# reranker ties. Tighten once the suite has a few nightly runs behind it.
_BASELINE_TOLERANCE = 0.05


@dataclass
class RowResult:
    id: str
    question: str
    expected_sources: List[str]
    retrieved_sources: List[str]
    recall_at_1: float
    recall_at_5: float
    reciprocal_rank: float
    hit: float
    predicted_answer: Optional[str] = None
    judge_score: Optional[int] = None
    judge_reason: Optional[str] = None


def _load_dataset(limit: Optional[int]) -> List[dict]:
    rows: list[dict] = []
    with open(_DATASET, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows if limit is None else rows[:limit]


def _load_docs() -> Dict[str, str]:
    from rag.ingest import extract_text_from_file

    docs: dict[str, str] = {}
    for fname in sorted(os.listdir(_DOCS_DIR)):
        path = _DOCS_DIR / fname
        if not path.is_file():
            continue
        docs[fname] = extract_text_from_file(str(path))
    if not docs:
        raise RuntimeError(f"No seed docs found in {_DOCS_DIR}")
    return docs


def _ingest(docs: Dict[str, str]) -> None:
    from rag.ingest import ingest_documents
    from rag.user_store import wipe_namespace

    # Wipe the on-disk dir so FAISS / BM25 / storage-meta don't carry over.
    wipe_namespace(_EVAL_NAMESPACE)
    ingest_documents(docs, user_id=_EVAL_NAMESPACE)


def _run_row(row: dict, *, judge: bool) -> RowResult:
    from rag.retrieve import retrieve_top_chunks

    chunks = retrieve_top_chunks(row["question"], top_k=_TOP_K, user_id=_EVAL_NAMESPACE)
    retrieved_sources = [c["source"] for c in chunks]
    expected = row["source_docs"]

    result = RowResult(
        id=row["id"],
        question=row["question"],
        expected_sources=expected,
        retrieved_sources=retrieved_sources,
        recall_at_1=recall_at_k(retrieved_sources, expected, k=1),
        recall_at_5=recall_at_k(retrieved_sources, expected, k=5),
        reciprocal_rank=reciprocal_rank(retrieved_sources, expected),
        hit=hit_rate(retrieved_sources, expected),
    )

    if judge:
        from evals.judge import score_answer
        from rag.generate import generate_answer

        predicted = generate_answer(row["question"], chunks)
        result.predicted_answer = predicted
        scored = score_answer(row["question"], row["expected_answer"], predicted)
        if scored is not None:
            result.judge_score = scored["score"]
            result.judge_reason = scored["reason"]

    return result


def _summary(rows: List[RowResult]) -> Dict[str, float]:
    dicts = [asdict(r) for r in rows]
    agg = aggregate([
        {
            "recall_at_1": r["recall_at_1"],
            "recall_at_5": r["recall_at_5"],
            "reciprocal_rank": r["reciprocal_rank"],
            "hit": r["hit"],
        }
        for r in dicts
    ])
    judge_scores = [r["judge_score"] for r in dicts if r["judge_score"] is not None]
    if judge_scores:
        agg["judge_mean"] = sum(judge_scores) / len(judge_scores)
        agg["judge_n"] = float(len(judge_scores))
    return agg


def _render_markdown(summary: Dict[str, float], rows: List[RowResult], meta: Dict) -> str:
    lines = [
        "# RAG Evaluation",
        "",
        f"- Dataset: {meta['dataset_rows']} questions",
        f"- Timestamp: {meta['timestamp']}",
        f"- Mode: {meta['mode']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Recall@1 | {summary.get('recall_at_1', 0):.3f} |",
        f"| Recall@5 | {summary.get('recall_at_5', 0):.3f} |",
        f"| MRR | {summary.get('reciprocal_rank', 0):.3f} |",
        f"| Hit rate (top-{_TOP_K}) | {summary.get('hit', 0):.3f} |",
    ]
    if "judge_mean" in summary:
        lines.append(f"| LLM-judge mean (0-5) | {summary['judge_mean']:.2f} (n={int(summary['judge_n'])}) |")
    lines += ["", "## Per-row", "", "| id | Recall@1 | Recall@5 | RR | Judge |", "|---|---|---|---|---|"]
    for r in rows:
        judge_cell = "–" if r.judge_score is None else str(r.judge_score)
        lines.append(
            f"| {r.id} | {r.recall_at_1:.2f} | {r.recall_at_5:.2f} | "
            f"{r.reciprocal_rank:.2f} | {judge_cell} |"
        )
    return "\n".join(lines) + "\n"


def _write_results(summary: Dict[str, float], rows: List[RowResult], meta: Dict) -> Path:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = meta["timestamp"]
    json_path = _RESULTS_DIR / f"{ts}.json"
    md_path = _RESULTS_DIR / f"{ts}.md"
    payload = {"meta": meta, "summary": summary, "rows": [asdict(r) for r in rows]}
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(summary, rows, meta), encoding="utf-8")
    return json_path


def _baseline_check(summary: Dict[str, float]) -> bool:
    if not _BASELINE_PATH.exists():
        log.warning("evals.baseline_missing", path=str(_BASELINE_PATH))
        return True
    baseline = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    threshold = float(baseline.get("recall_at_5", 0.0)) - _BASELINE_TOLERANCE
    observed = float(summary.get("recall_at_5", 0.0))
    ok = observed >= threshold
    log.info(
        "evals.baseline_check",
        observed=round(observed, 3),
        baseline=baseline.get("recall_at_5"),
        threshold=round(threshold, 3),
        passed=ok,
    )
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RAG evaluation harness.")
    parser.add_argument("--smoke", action="store_true", help="Run first 5 rows only (CI PR smoke).")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N rows.")
    parser.add_argument("--judge", action="store_true", help="Run LLM-as-judge pass (costs OpenAI tokens).")
    parser.add_argument("--baseline-check", action="store_true", help="Exit non-zero if Recall@5 drops below baseline.")
    args = parser.parse_args(argv)

    limit = 5 if args.smoke else args.limit
    rows_in = _load_dataset(limit)
    log.info("evals.start", rows=len(rows_in), judge=args.judge, smoke=args.smoke)

    _ingest(_load_docs())

    t0 = time.time()
    results: list[RowResult] = []
    for row in rows_in:
        results.append(_run_row(row, judge=args.judge))
    elapsed = time.time() - t0

    summary = _summary(results)
    meta = {
        "timestamp": time.strftime("%Y%m%dT%H%M%S", time.gmtime()),
        "dataset_rows": len(results),
        "mode": "smoke" if args.smoke else ("full+judge" if args.judge else "full"),
        "elapsed_seconds": round(elapsed, 2),
        "top_k": _TOP_K,
    }
    json_path = _write_results(summary, results, meta)
    log.info("evals.done", summary=summary, output=str(json_path))
    print(json.dumps({"summary": summary, "output": str(json_path)}, indent=2))

    if args.baseline_check and not _baseline_check(summary):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
