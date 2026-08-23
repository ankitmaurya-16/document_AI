# Runbook

Operational playbooks for running DocAI in anger. Each entry follows the same shape: **symptom → first check → action → verify**.

## Dashboards

- Grafana: http://localhost:3000 (profile `observability`)
- Jaeger: http://localhost:16686 (profile `observability`)
- Prometheus: http://localhost:9090 (profile `observability`)
- Raw metrics: http://localhost:5001/metrics

---

## 1. `/metrics` error rate above threshold

**Symptom.** Grafana alert on the error-rate panel: `sum(rate(flask_http_request_total{status=~"5.."}[5m])) / sum(rate(flask_http_request_total[5m])) > 0.05`.

**First check.**
- `curl -s localhost:5001/metrics | grep flask_http_request_total` — which endpoint?
- Jaeger: filter `service=docai-backend tags.error=true` over the last 15 min.
- Logs: `docker compose logs backend | grep -E 'ERROR|"level":"error"'`

**Action.**
- If a single route dominates → roll back the most recent deploy touching that route.
- If spike follows an OpenAI incident (check status.openai.com), flip `OPENAI_API_KEY` to the degraded-mode key or disable `/api/v1/chat` at the edge.
- If errors are `credits_exhausted` 402s, it's organic — not an incident.

**Verify.** Watch the error rate panel for 5 min — it should return below 1 %.

---

## 2. Stripe webhook dead — credits not landing

**Symptom.** User reports paying but credits didn't appear.

**First check.**
- Stripe dashboard → Developers → Webhooks → target endpoint → delivery history. Are events arriving?
- Backend logs: `docker compose logs backend | grep stripe.webhook`
- Mongo: `db.processed_events.find({ event_id: "<event id>" })`

**Action.**
- **Delivered, 4xx signature error:** `STRIPE_WEBHOOK_SECRET` is stale. Rotate in Stripe, update env, redeploy, then in Stripe click "Resend" on the affected events.
- **Delivered, 200, but no credit:** inspect the event payload — missing `metadata.user_id` means an old checkout session predates metadata wiring. Credit manually:
  ```
  db.users.updateOne({_id: ObjectId("<user>")}, { $inc: { credits: 500 } })
  ```
- **Not delivered:** Stripe shows the attempt failed — check the edge. Is the public URL reachable?

**Verify.** Replay the event from Stripe; check `processed_events` has a row; check the user's `credits` increased by the expected amount exactly once.

---

## 3. Drain a bad ingest from the DLQ

**Symptom.** `failed_ingests` collection grows; user complains their upload never became searchable.

**First check.**
```
db.failed_ingests.find({ user_id: "<user>" }).sort({ failed_at: -1 })
```
Each record carries `job_id`, `user_id`, `error`, `error_type`, and `failed_at` (written by
`_record_dead_letter` in [backend/tasks/ingest_tasks.py](backend/tasks/ingest_tasks.py)).
Typical causes: OpenAI 5xx storm, PDF parse error, file exceeds quota. Note that
`ValueError` (unsupported format, unparseable file) is deliberately *not* in `autoretry_for`
— it fails fast and lands here on the first attempt.

**Action.**
- **Transient (OpenAI 5xx, network):** re-queue the task.
  ```
  # signature: (job_id, file_paths, total_bytes, user_id)
  docker compose exec worker celery -A tasks.celery_app call tasks.ingest.run \
    --args='["<new-job-id>", [], 0, "<user_id>"]'
  ```
  Passing an empty `file_paths` is intentional for an authenticated user: the task
  re-ingests the user's whole corpus from the raw store, so the temp paths from the
  original request are not needed.
- **Hard parse error:** the `documents` collection has no status field today (see
  `insert_document` in [backend/rag/database.py](backend/rag/database.py)), so the row still
  reads as a normal upload while the chunks are missing from the index. Until a status field
  exists, delete the row so the UI stops listing a document that isn't searchable:
  ```
  db.documents.deleteOne({ _id: ObjectId("<id>") })
  ```
- **Over quota:** ask the user to delete docs, then manually retry.

**Verify.** The replayed job reaches `succeeded` at `GET /api/v1/chat/jobs/<job_id>`, and asking a question that should hit the document returns it in `sources`. Delete the `failed_ingests` row once resolved.

---

## 4. Ingest queue backed up

**Symptom.** `docker compose exec redis redis-cli llen celery` climbing; uploads stay `pending` at `GET /api/v1/chat/jobs/<job_id>` for minutes.

**First check.**
- `docker compose ps` — is the worker healthy?
- `docker compose logs worker --tail=200` — is it actually processing, or stuck on one task?
- Grafana ingest-duration panel (`docai_ingestion_duration_seconds`) — is the p95 huge? Remember every upload re-embeds the user's entire corpus, so p95 grows with the largest account.

**Action.**
- **Worker crashed or OOM:** `docker compose restart worker`. `acks_late=True` means in-flight tasks re-enqueue.
- **One stuck task (> 10 min):** `celery -A tasks.celery_app control revoke <task-id> --terminate`.
- **Genuinely under-provisioned:** scale workers: `docker compose up -d --scale worker=3`.

**Verify.** Queue length trends toward zero within a few minutes and job status moves `pending` → `running` → `succeeded`.

---

## 5. Retrieval quality regression (eval CI job failed)

**Symptom.** `evals-smoke` CI job fails on a PR with `Recall@5 dropped below baseline`.

**First check.**
- The artifact `evals-smoke-results/` on the failing run. Look at per-question rows — which expected doc did we miss?
- Diff the PR against `main` on [backend/rag/](backend/rag/) — what retrieval parameter changed?

**Action.**
- If the regression is *intentional* (e.g., bumping `CHUNK_SIZE` to fit a different model), run the full eval locally, update `backend/evals/baseline.json` in the PR, and note the tradeoff in the PR description.
- Otherwise, revert the offending change and re-run.

**Verify.** Re-push; `evals-smoke` green.

---

## 6. Restart / drain gracefully

**Symptom.** Deploy time, or a host needs patching.

**Action.**
- `docker compose stop backend` — gunicorn has `graceful_timeout=30`, so in-flight requests finish.
- `docker compose stop worker` — Celery's `worker_shutting_down` handler closes OTel + Qdrant, then the worker drains.
- `docker compose up -d backend worker` — back up.

**Verify.**
- No 502s visible at the edge during the rolling stop.
- `docker compose logs worker` shows the clean-shutdown log lines.

---

## 7. Mongo slow queries / missing index

**Symptom.** p95 latency climbs on `/api/v1/documents` or `/api/v1/chat`.

**First check.**
```
db.setProfilingLevel(1, { slowms: 100 })
# ... let traffic run ...
db.system.profile.find().sort({ ts: -1 }).limit(20)
```

**Action.**
- Add the missing index. Collection indexes are created idempotently on boot in [backend/rag/database.py](backend/rag/database.py); the Stripe-specific `processed_events` indexes live in `_ensure_processed_events_index` in [backend/routes/v1/billing.py](backend/routes/v1/billing.py). Note `failed_ingests` currently has no index — add one on `user_id` before the DLQ grows.

**Verify.** Re-run the query via `explain("executionStats")` — the plan should be `IXSCAN` and `executionTimeMillis` < 50.

---

## 8. Secret leaked

See [SECURITY.md](SECURITY.md) § Rotation checklist.

---

## Healthchecks

| Endpoint | Meaning |
|---|---|
| `GET /api/v1/health` | Process alive; does **not** guarantee DB reachable |
| `GET /metrics` | Prometheus scrape target; high `process_resident_memory_bytes` = leak |
| `docker compose ps` healthcheck column | Compose probes (`mongosh ping`, `redis-cli ping`, `curl /minio/health/live`) |
