# Contributing

Thanks for looking! This is a portfolio project, but PRs that sharpen reliability, security, or test coverage are welcome.

## Dev setup

```bash
git clone <repo>
cd <repo>
cp .env.docker.example .env.docker   # fill in OPENAI_API_KEY + JWT_SECRET
docker compose up --build
```

If you want to iterate against the backend without rebuilding containers:

```bash
# Terminal 1 — backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)
python app.py

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

## Running tests

Backend unit + coverage gate:

```bash
cd backend
pytest -q --cov=. --cov-config=.coveragerc --cov-fail-under=50
```

Backend integration (needs Docker running):

```bash
pytest -m integration tests/integration -q
```

Frontend unit (vitest):

```bash
cd frontend
npm test            # one-shot run
npm run test:watch  # TDD loop
npm run test:coverage
```

End-to-end (Playwright against docker-compose):

```bash
docker compose up -d mongo redis backend frontend
cd frontend
npx playwright install chromium
npx playwright test
```

RAG eval harness:

```bash
cd backend
python -m evals.run --smoke            # 5 questions, retrieval only
python -m evals.run                    # 30 questions + LLM-as-judge (needs real OPENAI_API_KEY)
```

## Linters & security

```bash
# Backend
cd backend
ruff check . --exclude data
bandit -r . -ll --exclude ./data,./tests
pip-audit --strict

# Frontend
cd frontend
npm run lint
```

CI runs all of the above. `ruff` blocks CI; `pip-audit` is report-only until the existing surface is triaged (see [README.md](README.md) § Security).

## Commit conventions

- Use imperative mood: `add`, `fix`, `update`, not `added`/`fixing`.
- One logical change per commit. If you find yourself writing `and` in the subject line, split it.
- Reference the ADR number for architecture-touching changes: `vectors: switch default to HNSW M=32 (ADR-0001)`.

We don't enforce Conventional Commits, but consistent subjects make `git log` readable.

## PR checklist

Before requesting review:

- [ ] `pytest` passes locally
- [ ] `npm test` passes locally
- [ ] `ruff check .` and `npm run lint` pass
- [ ] New features include tests (unit + integration where reasonable)
- [ ] New external calls use `with_retry(...)` from [backend/resilience.py](backend/resilience.py)
- [ ] New metrics follow the `docai_<subsystem>_<metric>_<unit>` naming in [backend/metrics.py](backend/metrics.py)
- [ ] Structural changes include an ADR under [docs/adr/](docs/adr/)
- [ ] README / ARCHITECTURE updated if user-visible surface changed

## What's out of scope

- Sweeping refactors without an ADR.
- Switching the LLM provider wholesale (add an adapter instead).
- Features behind paid-only services (we try to keep the whole repo runnable for free).
