# ADR 0003 — Async ingestion: Celery over RQ / asyncio

Date: 2026-04
Status: Accepted

## Context

Document ingestion (parse → chunk → embed → upsert) can take 30 s per file when the doc is large. Doing it inline in the HTTP request blocks the worker pool and trips request timeouts at the edge.

Options:

1. **Celery + Redis** — battle-tested, supports retries, ACKs late, dead-letter via routing.
2. **RQ** — lighter, pure-Python, simpler.
3. **asyncio inside the same process** — no new infra; run long jobs as background tasks.

## Decision

**Celery + Redis, opt-in via `ASYNC_MODE=celery`; sync fallback otherwise.**

The upload endpoint checks `ASYNC_MODE` at runtime. When `celery`, it enqueues and returns 202. When unset, it runs ingest inline — fine for small docs and local dev.

Task config in [backend/tasks/ingest_tasks.py](backend/tasks/ingest_tasks.py):

- `autoretry_for=(openai.APIError, ConnectionError)`
- `retry_backoff=True`, `max_retries=5`
- `acks_late=True` so a worker crash re-enqueues the task
- Permanent failures write to `failed_ingests` (the DLQ)

## Consequences

**Good**
- Large ingests don't block the API.
- Built-in retry/backoff + ACKs-late = no silent data loss on worker crashes.
- The sync fallback keeps local dev instant.

**Bad**
- Celery is one more moving part (broker, worker process, config).
- Debugging async retries is harder than inline calls — mitigated by OTel tracing through the enqueue boundary.

**Why not RQ**
- RQ retries are newer and less feature-rich; no built-in DLQ routing; smaller community. The existing Celery muscle-memory wasn't worth giving up.

**Why not asyncio-in-process**
- Background asyncio tasks die with the process. No retries, no durable queue, no multi-worker fan-out. Fine for "fire a log line" — not for "re-embed a 200-page PDF."
