# DocAI — Document Q&A with RAG

A full-stack Retrieval-Augmented Generation system: upload documents, ask natural-language questions, get answers with source citations. Built with the operational practices a real service needs — structured logging, distributed tracing, Prometheus metrics, bounded retries on every external call, a scored evaluation harness for retrieval quality, integration tests against real datastores, and a security-linted CI pipeline.

---

## Highlights

- **RAG pipeline** — hybrid retrieval (FAISS HNSW + BM25 fused via RRF), optional cross-encoder reranker, inline source citations
- **Auth** — JWT + bcrypt, Google OAuth, per-route rate limiting
- **Storage** — MongoDB for chats / users / feedback / documents, optional Qdrant for vectors, optional S3/MinIO for raw files
- **Async ingestion** — opt-in via `ASYNC_MODE=celery`; Celery + Redis workers, retries with exponential backoff, failed jobs land in a dead-letter collection
- **Billing** — Stripe Checkout (test mode); webhook is idempotent by `event_id` so retries never double-credit
- **Observability** — OpenTelemetry traces → Jaeger, `/metrics` for Prometheus, a provisioned Grafana dashboard
- **Reliability** — `tenacity` retries + timeouts on every OpenAI / Stripe / Qdrant / S3 call, security-headers middleware, PII-redacting log processor, graceful shutdown in gunicorn + Celery
- **Quality gates** — ruff, bandit, pip-audit, trivy, pytest coverage ≥ 50 %, vitest, Playwright E2E, testcontainers integration suite
- **Measured retrieval** — nightly eval harness scores Recall@K, MRR, and LLM-as-judge answers against a 30-question golden dataset

---

## Live demo
<video src="https://github.com/user-attachments/assets/fe85bf3e-4a40-4713-abc4-6f235b80201f" controls width="800"></video>

Not hosted right now — run it locally with `docker compose up --build`. The intended cloud topology is sketched in [ARCHITECTURE.md](ARCHITECTURE.md) § Deployment topology.

---

## Quickstart

Prereqs: Docker + Docker Compose, and an OpenAI API key (or `sk-test-…` for routes that don't need real LLM).

```bash
cp .env.docker.example .env.docker
# Fill in OPENAI_API_KEY and JWT_SECRET at minimum.

docker compose up --build
```

Open http://localhost:5173 — register an account, upload a document, ask a question.

Optional profiles:

```bash
docker compose --profile observability up     # + Jaeger, Prometheus, Grafana
docker compose --profile celery up            # + async ingest worker
docker compose --profile qdrant up            # swap FAISS → Qdrant
docker compose --profile minio up             # swap local disk → S3-compatible object store
```

---

## Architecture

C4 context + container diagrams and request-path sequence diagrams are in [ARCHITECTURE.md](ARCHITECTURE.md). Four architectural decisions are captured in [docs/adr/](docs/adr/): vector store choice, object store choice, async framework, web framework.

```
browser ──► Nginx (frontend) ──► Flask (backend) ──► Mongo
                                       │         ──► Redis ──► Celery worker
                                       │         ──► FAISS | Qdrant
                                       │         ──► local disk | MinIO | S3
                                       │         ──► OpenAI / Stripe
                                       └── OTel ─► Jaeger
                                       └── /metrics ─► Prometheus ─► Grafana
```

---

## Retrieval quality

The retriever is measured, not just shipped. The golden dataset lives at [backend/evals/dataset/golden.jsonl](backend/evals/dataset/golden.jsonl) — 30 questions across 5 seed docs.

```bash
cd backend
python -m evals.run                 # full run with LLM-as-judge
python -m evals.run --smoke          # 5 questions, retrieval only
```

The CI `evals-smoke` job runs a 5-question subset on every PR and compares Recall@5 against [backend/evals/baseline.json](backend/evals/baseline.json); a drop of more than 0.05 fails the job. That baseline is still a hand-set placeholder (0.80) — it needs replacing with the median of a few nightly runs before the gate means much. The nightly workflow runs the full 30-question scored eval and uploads results as an artifact.

Methodology, scoring rubric, and the LLM-judge prompt are documented in [backend/evals/README.md](backend/evals/README.md).

### Cache effectiveness

Two layers sit in front of the LLM call in [backend/cache.py](backend/cache.py): an exact layer keyed on a SHA-256 of the normalised query (1 h TTL), and a semantic layer that reuses an answer when the query embedding is within 0.93 cosine of a cached one (30 min TTL). A hit on either skips retrieval *and* generation.

| Path | Median latency | LLM prompt tokens | Runs |
|---|---|---|---|
| Miss (embed → hybrid retrieve → rerank → LLM) | **1.123 s** | 519 | 12 |
| Exact-cache hit (identical query) | **0.007 s** | 0 | 7 |
| Semantic-cache hit (reworded query) | **0.016 s** | 0 | 9 |

A served hit is ~168× faster than a miss on the exact layer and ~69× on the semantic layer, and costs zero prompt tokens because the provider is never called. Miss latency ranged 0.49–1.67 s; the median is reported.

**Method.** Single user, one 1,434-byte plain-text document indexed into 5 chunks, questions answered against it over HTTP. Each request was classified by diffing the `docai_cache_hit_total{layer}` / `docai_cache_miss_total{layer}` counters on `/metrics` around the call, never by timing, and token counts came from a pass-through proxy recording `usage.prompt_tokens` (the app records none). Reranking enabled, cache backend in-memory (no `REDIS_URL`), LLM `openai/gpt-oss-120b` via Groq. Measured on an Apple M3 (8-core, 8 GB, macOS 26.6.2), Python 3.12.7.

**One caveat worth stating.** At 0.93 the semantic layer only catches near-duplicate phrasings, not genuine paraphrases. Measured against *"How does the platform combine vector search with keyword search?"*: reworded-but-recognisable variants scored 0.977–0.998 and hit, while true paraphrases such as *"How are vector search results and keyword search results fused together?"* (0.892) and *"In what way does the system merge dense retrieval with BM25 keyword search?"* (0.625) fell below the threshold and missed. The semantic latency above is therefore the cost of a near-duplicate hit; the layer's real-world hit rate depends on how often users re-ask in nearly the same words.

These are local single-user numbers on one document, not production data. They measure what the cache saves when it hits, not how often it hits.

---

## Reliability

Every external call is wrapped with bounded exponential backoff via `tenacity` ([backend/resilience.py](backend/resilience.py)):

| Failure mode | How it's handled | Where |
|---|---|---|
| OpenAI API transient error | 3 attempts, expo backoff capped at 10 s, 30 s request timeout | [backend/rag/generate.py](backend/rag/generate.py) |
| Stripe 5xx / rate-limit | `with_retry("stripe")` on `checkout.Session.create` | [backend/routes/v1/billing.py](backend/routes/v1/billing.py) |
| Qdrant network hiccup | retry wrapper on upsert / search | [backend/rag/vector_store.py](backend/rag/vector_store.py) |
| S3 / MinIO boto3 errors | boto3 `standard` retry mode | [backend/storage.py](backend/storage.py) |
| Stripe webhook re-delivery | unique index on `processed_events.event_id` (+ 30-day TTL) — duplicate insert short-circuits with 200 | [backend/routes/v1/billing.py](backend/routes/v1/billing.py) |
| Celery ingest failure | `autoretry_for=(APIError, ConnectionError)`, `retry_backoff=True`, `acks_late`; permanent failures logged to `failed_ingests` | [backend/tasks/ingest_tasks.py](backend/tasks/ingest_tasks.py) |
| SIGTERM during request | `graceful_timeout=30` in gunicorn; Celery flushes OTel + closes clients on `worker_shutting_down` | [backend/gunicorn.conf.py](backend/gunicorn.conf.py) |

A `docai_external_retry_total{service}` counter in [backend/metrics.py](backend/metrics.py) surfaces retry rates in Grafana.

---

## Observability

- **Traces** — OpenTelemetry auto-instruments Flask / requests / PyMongo / Redis. Exports to OTLP over HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise no-op. Jaeger UI at http://localhost:16686 under the `observability` profile.
- **Metrics** — `/metrics` exposes Prometheus counters + histograms (app-level RAG counters live in [backend/metrics.py](backend/metrics.py)). Prometheus scrapes the backend; Grafana dashboard auto-provisioned from [monitoring/grafana/dashboards/](monitoring/grafana/dashboards/).
- **Logs** — structlog with a PII-redacting processor in [backend/logging_config.py](backend/logging_config.py). JSON in prod; pretty console in dev.

---

## Security

- **Headers** — CSP, HSTS, X-Frame-Options: DENY, X-Content-Type-Options, Referrer-Policy, Permissions-Policy via [backend/middleware/security.py](backend/middleware/security.py).
- **Auth** — JWT signed with `JWT_SECRET`; bcrypt password hashing; Google OAuth token exchange server-side.
- **Rate limits** — per-route limits in [backend/extensions.py](backend/extensions.py) (auth 10/min, chat 30/min, upload 10/min, default 200/hour), keyed on user id when authenticated and IP otherwise. Storage defaults to `memory://`, which is per-process — set `RATELIMIT_STORAGE_URI` to Redis before running multiple workers.
- **Upload hardening** — magic-byte sniffing, extension allow-list, per-file size cap, per-user storage quota. Malware scanning is a no-op hook (`scan_for_malware`) pending a ClamAV daemon.
- **PII redaction** — log processor regex-redacts emails, bearer tokens, and card-number-shaped digits before the JSON renderer.
- **Supply chain** — Dependabot ([.github/dependabot.yml](.github/dependabot.yml)), bandit security lint, pip-audit for CVEs, trivy filesystem scan in CI.
- **Threat model + disclosure** — [SECURITY.md](SECURITY.md).

---

## Testing

| Suite | Location | CI job |
|---|---|---|
| Backend unit | [backend/tests/](backend/tests/) | `backend` |
| Backend coverage gate | `.coveragerc` + `--cov-fail-under=50` | `backend` |
| Backend integration (testcontainers + real Mongo) | [backend/tests/integration/](backend/tests/integration/) | `integration` |
| Frontend unit (vitest) | [frontend/src/**/__tests__/](frontend/src/) | `frontend-unit` |
| E2E (Playwright vs docker-compose) | [frontend/tests/e2e/](frontend/tests/e2e/) | `e2e` |
| RAG eval smoke | [backend/evals/](backend/evals/) | `evals-smoke` |
| RAG eval nightly | same | scheduled workflow |

Runbook entries for common ops tasks (restart a stuck ingest, drain the DLQ, inspect Celery queues) live in [RUNBOOK.md](RUNBOOK.md).

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind, React Router |
| Backend | Flask 3, Python 3.12, gunicorn |
| Embeddings | `sentence-transformers` (all-MiniLM-L6-v2) |
| Vector search | FAISS HNSW (default) or Qdrant |
| Lexical search | BM25 (rank-bm25) fused with dense via Reciprocal Rank Fusion |
| LLM | OpenAI `gpt-4o-mini` (configurable) |
| Auth | JWT (PyJWT), bcrypt, Google OAuth |
| Primary DB | MongoDB 7 |
| Cache / broker | Redis 7 |
| Async jobs | Celery 5 |
| Object storage | local disk, S3, or MinIO |
| Billing | Stripe Checkout (test mode) |
| Tracing | OpenTelemetry + Jaeger |
| Metrics | Prometheus + Grafana |
| Logs | structlog (JSON) |

---

## Configuration

Settings resolve through [backend/settings.py](backend/settings.py). A minimal dev `.env`:

```env
OPENAI_API_KEY=sk-...
MONGODB_URI=mongodb://localhost:27017
JWT_SECRET=change-me
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Tunable RAG knobs live in [backend/rag/config.py](backend/rag/config.py): chunk size (400) / overlap (50), top-K, embedding model. It is imported as bare `config` because `backend/rag` is placed on `sys.path` at boot — a wart worth cleaning up.

---

## API

Full schema in [backend/docs/API.md](backend/docs/API.md). Versioned under `/api/v1/`:

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/register` | email + password |
| POST | `/api/v1/auth/login` | email + password |
| POST | `/api/v1/auth/google` | Google OAuth access token |
| GET | `/api/v1/auth/verify` | token → current user |
| POST | `/api/v1/chat` | ask (text only) |
| POST | `/api/v1/chat/upload` | ask + upload files in one turn |
| POST | `/api/v1/upload` | upload only |
| GET / DELETE | `/api/v1/documents[/<id>]` | user's docs |
| POST | `/api/v1/feedback` | thumbs up / down / clear |
| GET | `/api/v1/billing/plans` | plan metadata |
| POST | `/api/v1/billing/create-checkout-session` | Stripe Checkout |
| POST | `/api/v1/billing/webhook` | Stripe → server |
| GET | `/api/v1/health` | liveness |
| GET | `/metrics` | Prometheus |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, lint/test commands, and commit conventions.

---

## License

MIT — see [LICENSE](LICENSE).
