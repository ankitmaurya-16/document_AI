# ADR 0002 — Object storage: MinIO in dev, direct S3 in prod

Date: 2026-04
Status: Accepted

## Context

Raw uploads (PDFs, docx, pptx, images) need to live somewhere. The ingest worker re-reads the bytes asynchronously, so the storage layer must be reachable from both the API and the worker.

Options:

1. **Local disk (shared volume)** — simplest; one container volume mounted into API + worker.
2. **Direct AWS S3** — production answer everywhere else in the industry.
3. **MinIO** — S3-compatible OSS server; runs in docker-compose.

## Decision

**Default to local disk; use MinIO in docker-compose when the `minio` profile is on; use S3 in prod when `S3_ENDPOINT`/`S3_BUCKET` are set.**

All three paths live behind [backend/storage.py](backend/storage.py). The backend picks a backend at boot based on env:

- `S3_ENDPOINT` set → boto3 against MinIO or S3
- otherwise → local filesystem under `/app/data`

## Consequences

**Good**
- Dev + unit tests need zero infra (just a tmpdir).
- MinIO proves the boto3 path works locally before prod.
- Switching dev → prod is an env-var change; no code touches.
- boto3 retries (`retry_mode=standard`) and the `with_retry` wrapper give the same backoff semantics as OpenAI/Stripe.

**Bad**
- The local-disk path doesn't exist at scale (multi-instance deploys must use S3/MinIO). Enforced at deploy time, not by the code.
- A third backend means per-backend quirks (e.g., MinIO is case-sensitive on bucket names even where S3 isn't).

**Why not "S3 only"**
- Portfolio repo should run with `docker compose up` and no cloud account.

**Why not "local disk only"**
- Multi-worker deployments need a shared object store; showing the S3 path documented + tested is part of the production-maturity story.
