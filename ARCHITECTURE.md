# DocAI — Architecture

This document captures the runtime shape of DocAI as an interview-ready reference. For the design decisions behind each choice see [docs/adr/](docs/adr/).

## System context (C4 L1)

```mermaid
C4Context
    title DocAI — System Context
    Person(user, "End user", "Uploads docs, asks questions")
    System(docai, "DocAI", "RAG Q&A over user-uploaded documents")
    System_Ext(openai, "OpenAI", "LLM + embeddings (optional)")
    System_Ext(stripe, "Stripe", "Test-mode billing")
    System_Ext(google, "Google OAuth", "Optional SSO")
    Rel(user, docai, "HTTPS, browser")
    Rel(docai, openai, "chat.completions + embeddings (retried)")
    Rel(docai, stripe, "checkout + webhooks (retried, idempotent)")
    Rel(docai, google, "OAuth token exchange")
```

## Container diagram (C4 L2)

```mermaid
C4Container
    title DocAI — Containers
    Person(user, "User")
    System_Boundary(app, "DocAI") {
        Container(nginx, "Nginx (frontend)", "Nginx + Vite build", "Serves SPA; proxies /api → backend")
        Container(backend, "Flask API", "Python 3.12, gunicorn", "Auth, chat, upload, billing, metrics")
        Container(worker, "Celery worker", "Python 3.12", "Async ingest + embedding")
        ContainerDb(mongo, "MongoDB", "7.0", "Users, chats, documents, feedback, processed_events, failed_ingests")
        ContainerDb(redis, "Redis", "7-alpine", "Celery broker, rate-limit store, cache")
        ContainerDb(vectors, "Vector index", "FAISS (default) / Qdrant", "HNSW dense index per-user namespace")
        ContainerDb(blobs, "Object store", "local disk / MinIO / S3", "Raw uploaded files")
        Container(prom, "Prometheus", "", "Scrapes /metrics")
        Container(grafana, "Grafana", "", "Dashboards + alerts")
        Container(jaeger, "Jaeger", "", "OTel trace collector")
    }
    System_Ext(openai, "OpenAI")
    System_Ext(stripe, "Stripe")

    Rel(user, nginx, "HTTPS")
    Rel(nginx, backend, "HTTP /api/v1/*")
    Rel(backend, mongo, "pymongo")
    Rel(backend, redis, "celery enqueue, rate-limit counters")
    Rel(backend, vectors, "search + upsert")
    Rel(backend, blobs, "put/get raw files")
    Rel(backend, openai, "HTTPS (tenacity retries)")
    Rel(backend, stripe, "HTTPS (tenacity retries, idempotent webhooks)")
    Rel(worker, mongo, "records ingest state")
    Rel(worker, vectors, "upsert chunks")
    Rel(worker, blobs, "read raw files")
    Rel(worker, openai, "embeddings (retried)")
    Rel(backend, prom, "/metrics (pulled)")
    Rel(backend, jaeger, "OTLP/HTTP (pushed)")
    Rel(worker, jaeger, "OTLP/HTTP (pushed)")
    Rel(prom, grafana, "datasource")
```

## Request path — a chat turn

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant N as Nginx
    participant F as Flask
    participant M as Mongo
    participant V as Vector store
    participant O as OpenAI

    U->>N: POST /api/v1/chat
    N->>F: proxy
    F->>F: JWT verify + rate-limit check
    F->>M: load chat history
    F->>V: hybrid retrieve (FAISS + BM25, RRF fused)
    F->>F: rerank (optional cross-encoder)
    F->>O: chat.completions (tenacity: 3 tries, expo backoff, 30 s)
    O-->>F: answer + sources
    F->>M: append user + assistant messages
    F->>M: decrement user credits
    F-->>U: { response, sources[], chatId }
```

## Async ingest path

```mermaid
sequenceDiagram
    autonumber
    participant U as Browser
    participant F as Flask
    participant R as Redis
    participant W as Celery
    participant S as Object store
    participant V as Vector store
    participant M as Mongo

    U->>F: POST /api/v1/upload (multipart)
    F->>S: put raw bytes
    F->>M: documents doc (status=queued)
    F->>R: enqueue ingest task
    F-->>U: 202 accepted
    W->>R: dequeue
    W->>S: read raw file
    W->>W: parse + chunk
    W->>O: embed chunks (retried)
    W->>V: upsert vectors (retried)
    W->>M: documents.status=ready  (or insert failed_ingests on exhaustion)
```

## Data model (selected collections)

| Collection | Key indexes | Purpose |
|---|---|---|
| `users` | `email` unique | Auth + credits |
| `chats` | `userId`, `updatedAt` | Conversation threads |
| `documents` | `userId`, `status` | Per-user upload registry |
| `feedback` | `{chatId,messageTimestamp}` unique | Thumbs up/down per message |
| `processed_events` | `event_id` unique, `receivedAt` TTL 30 d | Stripe webhook idempotency |
| `failed_ingests` | `userId`, `createdAt` | Celery DLQ |

## Boundaries where retries / idempotency live

1. **OpenAI / Stripe / Qdrant / S3** — `with_retry(...)` in [backend/resilience.py](backend/resilience.py).
2. **Stripe webhook** — `processed_events` collection with a unique index on `event_id`; duplicate insert returns 200 without re-crediting.
3. **Celery ingest task** — `autoretry_for=(openai.APIError, ConnectionError)`, `retry_backoff=True`, `acks_late=True`. On exhaustion the job inserts into `failed_ingests` and the worker moves on rather than blocking the queue.
4. **Graceful shutdown** — gunicorn `graceful_timeout=30`; Celery `worker_shutting_down` handler closes Qdrant and flushes OTel spans.

## Deployment topology (intended)

```mermaid
graph LR
    subgraph Edge
        CF[Cloudflare / Vercel]
    end
    subgraph Frontend
        FE[Vercel static build]
    end
    subgraph Backend Infra
        API1[Fly.io app: backend]
        W1[Fly.io app: celery-worker]
    end
    subgraph Managed data
        MA[Mongo Atlas M0]
        RE[Upstash Redis]
        QC[Qdrant Cloud]
    end
    CF --> FE
    CF --> API1
    API1 --> MA
    API1 --> RE
    API1 --> QC
    W1 --> MA
    W1 --> RE
    W1 --> QC
```

Current deploy is local `docker compose` only; Wave I hosted deploy is tracked in [docs/roadmap.md](docs/roadmap.md).

## See also

- [docs/adr/0001-vector-db.md](docs/adr/0001-vector-db.md) — Qdrant vs Pinecone vs FAISS
- [docs/adr/0002-object-store.md](docs/adr/0002-object-store.md) — MinIO vs direct S3
- [docs/adr/0003-async-framework.md](docs/adr/0003-async-framework.md) — Celery vs RQ vs asyncio
- [docs/adr/0004-web-framework.md](docs/adr/0004-web-framework.md) — Flask vs FastAPI
- [RUNBOOK.md](RUNBOOK.md) — operational playbooks
- [SECURITY.md](SECURITY.md) — threat model + disclosure
