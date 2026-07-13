# ADR 0001 — Vector database: Qdrant (optional) over Pinecone / FAISS-only

Date: 2026-04
Status: Accepted

## Context

The retriever needs a dense ANN index. Requirements:

- Zero-cost local dev, reproducible in docker-compose
- Per-user namespaces (no cross-user data leakage)
- A viable production path without a full rewrite
- Small enough operational surface for a solo maintainer

Three candidates:

1. **FAISS on local disk** — pure library; we already use it.
2. **Qdrant** — OSS vector DB, self-hostable, gRPC + REST, managed tier exists.
3. **Pinecone** — managed only; generous free tier but no local equivalent.

## Decision

**Default to FAISS HNSW on local disk; switch to Qdrant when `QDRANT_URL` is set.**

- Dev + CI use FAISS → no containers required for unit tests.
- Docker-compose runs Qdrant under a profile so docker-only setups can prove the other branch works.
- Production is intended to use managed Qdrant Cloud (free tier, 1 GB) once deployed.

FAISS is hidden behind the `rag.vector_store` interface along with Qdrant, so swapping the backend is a config change, not a code change.

## Consequences

**Good**
- Unit tests run without containers.
- Identical API surface locally and in prod means retrieval-quality evals transfer cleanly.
- No vendor lock-in: Qdrant is OSS, and FAISS is a library.

**Bad**
- Two backends means two code paths to maintain. Mitigated by a tiny adapter and integration tests that exercise both via compose profiles.
- FAISS on disk doesn't survive container restart unless the volume is mounted. Compose does this already.

**Why not Pinecone**
- No local equivalent → CI has to talk to a real cluster or mock. Both are worse than "run it in docker."
- Portfolio repo should not require proprietary credentials to demo.

**Why not FAISS-only**
- HNSW on disk starts to wobble above ~1 M vectors. Qdrant's on-disk HNSW + payload filtering scales further without hand-tuning IVF.
- Managed Qdrant gives us TLS, backups, auth out of the box — none of which FAISS-on-disk solves.
