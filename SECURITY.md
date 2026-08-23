# Security

## Reporting a vulnerability

If you believe you've found a security issue in DocAI, please **do not open a public GitHub issue.** Instead:

- Email the maintainer directly (see [CONTRIBUTING.md](CONTRIBUTING.md) for contact).
- Include a minimal reproduction, the affected commit SHA, and the potential impact.
- Allow up to 14 days for an initial response before public disclosure.

We don't run a bug bounty — this is a portfolio project — but credible reports get prompt fixes and credit in release notes if desired.

## Supported versions

Only `main` is maintained. Tagged releases are snapshots for demo purposes and do not receive backported fixes.

## Threat model (summary)

### In scope

| Asset | Threat | Mitigation |
|---|---|---|
| User passwords | Database leak → credential stuffing | bcrypt hashing with per-user salt |
| JWTs | Theft / replay | Short-ish expiry, `Authorization: Bearer` only, HTTPS at edge, no `localStorage` XSS-friendly paths in rendered HTML |
| User-uploaded files | Cross-user read / write | Namespaced paths (`/data/users/<userId>/...`); every route re-checks `userId == request.user_id` before serving |
| Vector indexes | Cross-user retrieval | Per-user namespace passed into every `retrieve_top_chunks` call; enforced at the store layer |
| Stripe credentials | Leak via logs | PII-redacting log processor strips bearer tokens + card-shaped digits before emission |
| Stripe webhooks | Forged request / replay | `stripe.Webhook.construct_event` verifies signature; `processed_events` collection with unique `event_id` index prevents double-credit on retry |
| OpenAI key | Exfiltration | Env-only; never echoed in error responses; CI has a scrubbed test key |
| Supply chain | Malicious dependency | Dependabot weekly PRs; pip-audit + trivy + bandit in CI; pinned versions in `requirements.txt` |

### Out of scope (documented)

- **DoS / rate abuse beyond Flask-Limiter defaults.** An attacker with unlimited IPs can exhaust quota. In prod this sits behind Cloudflare.
- **Physical compromise of a host.** Encryption at rest is the hosting provider's responsibility.
- **Browser extension / malicious device.** Session theft via a compromised client is not mitigated.
- **LLM prompt injection.** Retrieved documents are user-controlled by design. We don't claim safety against an attacker who uploads an adversarial PDF that redirects LLM output — mitigations are additive and called out in the roadmap (e.g., sandboxed system prompts, citation auditing).

## Hardening checklist (implemented)

- [x] HTTPS-ready security headers: CSP, HSTS, X-Frame-Options: DENY, X-Content-Type-Options, Referrer-Policy, Permissions-Policy (see [backend/middleware/security.py](backend/middleware/security.py))
- [x] bcrypt password hashing
- [x] JWT signing with `JWT_SECRET` (rotate on compromise)
- [x] Rate limits per-route (auth / chat / upload / default) via Flask-Limiter
- [x] Upload hardening: extension allow-list, MIME sniffing, per-user quota, size cap
- [x] Stripe webhook idempotency + signature verification
- [x] PII-redacting log processor
- [x] Bandit + pip-audit + trivy in CI
- [x] Dependabot updates for pip, npm, docker, github-actions
- [x] `.env` / `*.env.*` in `.gitignore`; example files hold no secrets

## Rotation checklist

When a secret is suspected of being leaked:

1. **`OPENAI_API_KEY`** — revoke in the OpenAI dashboard, issue a new key, update the host env.
2. **`JWT_SECRET`** — rotate; all existing tokens immediately invalidate (users re-login).
3. **`STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET`** — rotate in Stripe dashboard, redeploy, re-register webhook.
4. **`MONGODB_URI`** — change cluster user password, reissue connection string.
5. Audit `logs/` (or the observability backend) for requests in the leakage window.
