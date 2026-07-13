# ADR 0004 — Web framework: Flask over FastAPI (for now)

Date: 2026-04
Status: Accepted

## Context

The API is synchronous I/O bound against OpenAI, Mongo, and Qdrant. Two realistic picks:

1. **Flask** — sync, WSGI, mature ecosystem, already in the codebase.
2. **FastAPI** — async, ASGI, built-in Pydantic, automatic OpenAPI.

## Decision

**Stay on Flask.**

- We already use `pydantic` explicitly ([backend/schemas.py](backend/schemas.py)) and treat every request body with `parse_json(Model, request)`, so FastAPI's killer feature is already in the code.
- We already emit an OpenAPI-ish surface documented by hand in [backend/docs/API.md](backend/docs/API.md). Autogeneration isn't load-bearing here.
- The production bottleneck is OpenAI latency (1–6 s per call), not request-concurrency. Sync + gunicorn workers handle it fine.
- OTel auto-instrumentation for Flask is first-class and stable; FastAPI's is newer.
- Switching a shipping codebase mid-project costs more than it gains.

## Consequences

**Good**
- No rewrite; Wave F/G/H effort went into reliability and eval quality, not plumbing.
- Familiar to most Python reviewers.

**Bad**
- Can't trivially stream SSE from an `async def`; we build streaming responses via generator functions. Works, but less ergonomic.
- Per-request concurrency is bounded by gunicorn worker count. Acceptable at current scale; would need revisiting if we started to fan out many background HTTP calls per request.

**Trigger to revisit**
- If we add a second server-side HTTP integration per request (e.g., multi-tenant LLM calls), async/await becomes worth it and a FastAPI migration should be reconsidered.
