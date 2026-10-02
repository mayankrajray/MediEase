# M0 — Foundation: design notes

| Field | Value |
|---|---|
| Status | Active — Phase 2 (M0-P1 closed in #6) |
| Covers | NFR-12 (observability), NFR-15 (portability), groundwork for NFR-05/06/14 |
| Exit criterion | `make up` on a fresh clone → `GET /health` 200, `GET /ready` 200 (503 when db is down); CI green |

This milestone builds **no product features**. It builds the skeleton every later feature hangs
on, so that from M1 onward a bug can be traced from a browser click to a log line to a row.

---

## What we are building and why

| Piece | Why it exists now |
|---|---|
| Typed settings (Pydantic Settings) | CLAUDE.md "single source of truth for configuration"; fail fast on misconfiguration |
| JSON logging + `request_id` middleware | NFR-12; every later debugging session depends on it |
| Flask app factory (composition root) | Testable construction, no import-time side effects |
| `/health` and `/ready` | Compose and production need truthful liveness and readiness |
| SQLAlchemy engine + Alembic baseline | Every milestone after this adds migrations |
| `migrate` one-off service | Schema changes as a discrete step |
| Next.js shell + generated client | Proves the contract-first loop and the `/api` proxy (ADR-0006, ADR-0008) |
| Dockerfiles + CI | Reproducibility and the merge gate |

## Concepts to teach before code (CLAUDE.md "Teaching Expectations")

1. Application factory pattern and composition root.
2. Settings objects vs reading `os.environ` everywhere.
3. Structured logging and correlation IDs.
4. Liveness vs readiness.
5. Why migrations run outside the app process.
6. Next.js rewrites as a same-origin proxy.
7. Generating TypeScript types from OpenAPI.
8. Multi-stage Docker builds and non-root containers.

## Phases

### M0-P1 — Repository and local database (done, #6)

Files: repository skeleton (this planning pack), `docker-compose.yml` (db only), `Makefile`,
`.env.example`, `.gitignore`, `.editorconfig`.

Verify:
```bash
cp .env.example .env
make up
make ps        # db is "healthy"
make psql      # then:  select 1;   → 1
make down
```
Failure path: set `POSTGRES_PASSWORD=` (empty) in `.env` → `make up` refuses to start with
"set POSTGRES_PASSWORD in .env" (Compose's required-variable check), before any container runs.

### M0-P2 — API process, settings, logging, `/health`

Planned files (`apps/api/`):
```
pyproject.toml                      pinned deps: flask, gunicorn, pydantic, pydantic-settings,
                                    structlog (or stdlib json logging), python-ulid; dev: pytest, ruff, mypy
src/mediease_api/__init__.py
src/mediease_api/config/settings.py AppSettings (env, log level, database url, cookie flags, …)
src/mediease_api/config/logging.py  JSON formatter, context vars for request_id/clinic_id/user_id
src/mediease_api/delivery/middleware.py   request_id in/out, access log with duration
src/mediease_api/delivery/errors.py       error envelope + SYS_UNEXPECTED handler
src/mediease_api/delivery/http/platform.py   /health
src/mediease_api/bootstrap.py       create_app(settings) — the composition root
src/mediease_api/wsgi.py            gunicorn entry: create_app(load_settings())
tests/unit/config/test_settings.py
tests/integration/test_health.py
```

Settings validation rules: `APP_ENV ∈ {local, test, staging, production}`; in `staging` and
`production`, `COOKIE_SECURE` must be true and `LOG_LEVEL` cannot be `DEBUG`;
`DB_ECHO_PARAMS` must be false everywhere.

Verify: `curl -i localhost:8000/health` → `200`, body `{"status":"ok"}`, header `X-Request-ID`.
Sending `X-Request-ID: test-123` echoes `test-123`. Removing `DATABASE_URL` → process exits with
`config.invalid` naming the field.

### M0-P3 — Database readiness and migrations

Planned files: `adapters/db/engine.py`, `delivery/http/platform.py` (`/ready`), `alembic.ini`,
`migrations/env.py` (reads settings, not env vars), empty baseline revision, a **minimal
`apps/api/Dockerfile`** (python:3.12-slim, non-root; hardened in P5), and `migrate` + `api`
services in compose. `migrate` depends on `db` (`service_healthy`) and runs
`alembic upgrade head` with `restart: "no"`; `api` depends on `db` (`service_healthy`) and
`migrate` (`service_completed_successfully`). `make up` therefore runs migrations before the API
starts with no manual step; the `pgdata` volume is preserved. Verify that
`docker compose up -d --wait` exits 0 once `migrate` has exited 0 (NEXT_STEPS_PLAN.md §5).


`/ready` runs `SELECT 1` with a 2-second statement timeout; returns
`200 {"status":"ready","checks":{"database":"ok"}}` or
`503` with the error envelope `READY_DB_UNAVAILABLE` / `READY_DB_TIMEOUT`.

Verify: `make up` alone brings up `db` → `migrate` (exits 0) → `api` (healthy) — check with
`docker compose ps -a`; `make migrate` exits 0 and `alembic current` shows the baseline;
`docker compose stop db`
→ `/ready` returns 503 within ~2 s while `/health` stays 200.

### M0-P4 — Web shell

Planned files (`apps/web/`): Next.js App Router project (TypeScript strict, ESLint, Tailwind),
`next.config` rewrite `/api/:path*` → `${API_INTERNAL_URL}/api/:path*` plus `/health` and `/ready`
for the status page, `src/lib/api/` (generated types + fetch wrapper that adds `X-Request-ID`),
`src/app/status/page.tsx`, security headers.

Verify: `localhost:3000/status` shows "API: healthy · DB: ready · Ref: <request_id>"; stopping the
API shows a clear error state, not a blank page.

### M0-P5 — Containers and CI

Planned files: `apps/api/Dockerfile` hardened (multi-stage, non-root, gunicorn; the minimal
version exists from P3),
`apps/web/Dockerfile` (multi-stage, standalone output, non-root), full `docker-compose.yml`
(`db`, `migrate`, `api`, `web` with health-based `depends_on`), `.github/workflows/ci.yml` jobs
enabled, import-boundary check for the API.

Verify: fresh clone → `cp .env.example .env && make up` (one command, no manual migrate step) →
`db`, `api`, `web` healthy and `migrate` exited 0; open a PR →
lint, typecheck, test and build jobs green.

## Risks in this milestone
- Over-building: resist adding auth, ORM models or UI components "while we are here".
- Version drift: pin every dependency at the version installed and tested, and record it.
