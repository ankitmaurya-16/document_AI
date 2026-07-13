# DocAI v1 API

All routes are served under `/api/v1`.

- **Auth**: Bearer JWT in `Authorization: Bearer <token>`. Tokens are issued by the auth endpoints below.
- **Content types**: JSON unless explicitly multipart.
- **Errors**: uniform shape `{ "error": <human message>, "code": <machine code>, "details"?: <object|list> }` (see [errors.py](../errors.py)).
- **Rate limits**: per-endpoint via Flask-Limiter. Hitting a cap returns 429 with code `rate_limited`.
- **CORS**: restricted to `CORS_ALLOWED_ORIGINS`. Browsers must include credentials.
- **Correlation**: every response has `X-Request-ID`; clients may set it on request to propagate.

## Health

### `GET /api/v1/health`
200 → `{ "status": "ok" }`. Used by Docker healthchecks and CI smoke tests.

## Auth

### `POST /api/v1/auth/register`
Body: `{ name, email, password }` (password ≥ 8 chars).  
201 → `{ token, user: { _id, email, name, credits } }`.  
409 → `code: "validation_error"` if email already exists.

### `POST /api/v1/auth/login`
Body: `{ email, password }`.  
200 → `{ token, user }`. 401 on bad credentials.

### `POST /api/v1/auth/google`
Body: `{ access_token }` (Google OAuth access token).  
200 → `{ token, user }`. Auto-creates an account on first login.

### `GET /api/v1/auth/verify`
Headers: `Authorization`.  
200 → `{ user }`. 401 on invalid/expired token.

## Chats

### `GET /api/v1/chats`
200 → `{ chats: Chat[] }`, ordered by `updatedAt` desc. Served from the MongoDB compound index `(userId, updatedAt)`.

### `POST /api/v1/chats`
Body: `{ name? }`. 201 → `{ chat: Chat }`.

### `GET /api/v1/chats/:chatId`
200 → `{ chat: Chat }`. 404 if not owned by user.

### `DELETE /api/v1/chats/:chatId`
204 on success.

### `Chat` shape

```ts
interface Chat {
  _id: string;
  userId: string;
  name: string;
  messages: Message[];
  createdAt: string;  // ISO
  updatedAt: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: number;       // ms since epoch
  files?: string[];
  sources?: string[] | { source: string; text?: string }[];
  rating?: -1 | 0 | 1;
}
```

## RAG chat

Three entrypoints — pick one:

### `POST /api/v1/chat` (JSON, non-streaming)
Body: `{ prompt, chatId? }`. 200 → `{ response, sources, chatId }`. 402 with `credits_exhausted: true` when the caller is out of credits.

### `POST /api/v1/chat/upload` (multipart, non-streaming)
Fields: `prompt` (text), `chatId?` (text), `files` (one or many). Accepts PDF, DOCX, TXT, CSV, XLSX, PPT(X), and images (OCR). Ingestion runs synchronously in `sync` mode and async via Celery when `ASYNC_MODE=celery`. Response shape matches `/chat`.

### `POST /api/v1/upload` (multipart, no prompt)
Uploads and indexes files without issuing a chat turn. 200 → `{ status: "ok" }`.

### Streaming variant (SSE)
The streaming routes are mounted alongside `/chat` and emit `text/event-stream`. Each SSE event is a JSON frame:

```ts
type SSEFrame =
  | { type: "meta";  chatId: string; sources?: string[] | Source[] }
  | { type: "delta"; content: string }
  | { type: "done";  chatId: string }
  | { type: "error"; error: string; code?: string };
```

Clients should render `delta` chunks progressively and stop reading on `done` or `error`.

## Documents

### `GET /api/v1/documents`
200 → `{ documents: Document[] }` ordered by `uploadedAt` desc.

### `DELETE /api/v1/documents/:docId`
Deletes the raw file and rebuilds the user's vector index from the remaining docs. 200 → `{ status: "ok" }`.

```ts
interface Document { _id: string; filename: string; size: number; uploadedAt: string; }
```

## Feedback

### `POST /api/v1/feedback`
Body: `{ chatId, messageTimestamp, rating: -1 | 0 | 1, comment? }`.  
Upserts by `(chatId, messageTimestamp)` — resubmitting overwrites the prior rating. 200 → `{ status: "ok" }`.

## Billing (Stripe, test mode)

### `GET /api/v1/billing/plans`
Public. 200 → `{ plans: Plan[] }`. The price / credits / features are backend-defined so the UI can't be spoofed.

### `POST /api/v1/billing/create-checkout-session`
Body: `{ plan }` (plan `_id`).  
200 → `{ url }` — redirect the browser. 402 if Stripe is not configured.

### `POST /api/v1/billing/webhook`
Signed by Stripe (`Stripe-Signature` header + `STRIPE_WEBHOOK_SECRET`). Increments the user's credits on `checkout.session.completed`. Non-authenticated.

## Observability

### `GET /metrics`
Prometheus exposition (not under `/api/v1`). Scraped by the Prometheus service in the `observability` compose profile. Exposes `flask_http_request_*` histograms plus the custom metrics defined in [metrics.py](../metrics.py):

- `docai_ingestion_duration_seconds` (histogram)
- `docai_cache_hit_total{layer}` / `docai_cache_miss_total{layer}` (counters)
- `docai_credit_burn_total{route}` (counter)

Distributed traces are shipped via OTLP HTTP to Jaeger when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; see [telemetry.py](../telemetry.py).

## Error codes

| Code | Status | When |
|---|---|---|
| `validation_error` | 400 | Pydantic validation failed or business rule violated |
| `auth_error` | 401 | Missing / invalid token |
| `forbidden` | 403 | Caller authenticated but not allowed |
| `not_found` | 404 | Resource does not exist or not owned by caller |
| `credits_exhausted` | 402 | User has zero credits and tried a paid route |
| `rate_limited` | 429 | Flask-Limiter rule exceeded |
| `payload_too_large` | 413 | Upload > `MAX_UPLOAD_MB` |
| `internal_error` | 500 | Unhandled exception (message redacted in prod) |
