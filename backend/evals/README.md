# RAG Evaluation Harness

This directory lets us measure — with numbers, not vibes — whether the
retriever and the end-to-end RAG pipeline are working.

## What we measure

| Metric | Definition |
|---|---|
| **Recall@1** | fraction of expected source documents that appear as the top result |
| **Recall@5** | fraction of expected source documents that appear in the top 5 results |
| **MRR** | mean reciprocal rank of the first expected document in the retrieval list |
| **Hit rate** | fraction of questions where at least one expected document appears anywhere in the top-K |
| **LLM-judge mean** | mean 0–5 score from `gpt-4o-mini` comparing the pipeline's answer to the gold answer (rubric in `judge.py`) |

Scoring is done at the **document level** (matching on the `source` filename
of each retrieved chunk). This is the unit a human can reliably label;
chunk IDs shift whenever chunk size is tuned.

## Dataset

- `dataset/docs/` — 5 seed text files on distinctive topics (Python,
  MongoDB, HTTP, Kubernetes, Git).
- `dataset/golden.jsonl` — 30 questions (6 per doc) with an `expected_answer`
  and the list of `source_docs` that should appear in retrieval.

Each question is written so exactly one document is the correct source,
making document-level Recall@K a meaningful signal.

## Usage

Retrieval-only eval over all 30 rows (fast, no OpenAI cost):

```bash
cd backend
python -m evals.run
```

Full eval with LLM-as-judge (requires a real `OPENAI_API_KEY`):

```bash
python -m evals.run --judge
```

CI PR smoke — 5 rows, retrieval-only, exits non-zero if Recall@5 drops
below the committed baseline:

```bash
python -m evals.run --smoke --baseline-check
```

Results land as timestamped JSON + Markdown under `evals/results/`
(git-ignored).

## Baseline

`baseline.json` pins the Recall@5 floor the CI smoke is allowed to hit.
The smoke tolerance is 0.05 (see `_BASELINE_TOLERANCE` in `run.py`) to
absorb run-to-run noise from reranker ties. Bump the baseline only after
three consecutive nightly runs show the higher number.

## Known environment quirks

FAISS HNSW search can segfault on macOS + Anaconda + faiss-cpu 1.8.x
(numpy/BLAS linkage mismatch). This only affects local development on
Anaconda-based Mac Pythons; the CI Linux wheels and the Docker image
are unaffected. If you hit this locally, either (a) run the eval inside
the backend Docker image, or (b) use a venv off a non-Anaconda
python (e.g. `brew install python@3.12`).
