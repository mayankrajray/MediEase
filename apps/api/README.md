# apps/api — MediEase API and worker

Flask API (HTTP + webhooks) and the background worker, sharing one hexagonal Python package.
Architecture: `docs/ARCHITECTURE.md` §3. Rules for agents: `CLAUDE.md` in this folder.

## Status

M0-P2: package, typed settings, structured logging, request IDs, error envelope and `GET /health`.
Database readiness, migrations and the Dockerfile arrive in M0-P3
(see `docs/milestones/M0-foundation.md`).

## Layout

| Path | Layer | May import |
|---|---|---|
| `src/mediease_api/domain/` | Entities, value objects, state machines, domain errors | standard library only |
| `src/mediease_api/application/` | Use cases and job handlers | `domain`, `ports` |
| `src/mediease_api/ports/` | Interfaces (Protocols) | `domain` |
| `src/mediease_api/adapters/` | SQLAlchemy, messaging, storage, PDF, clock | anything inward + libraries |
| `src/mediease_api/delivery/` | Flask blueprints, webhooks, worker entrypoint, middleware | anything inward |
| `src/mediease_api/config/` | Typed settings and logging | libraries |
| `src/mediease_api/bootstrap.py` | Composition root (M0-P2) | everything |
| `migrations/` | Alembic (M0-P3) | adapters' models |
| `tests/` | unit, integration, tenancy, contract | everything |

## Commands

Run from the repository root inside WSL (or Linux/macOS) with Python 3.12 on `PATH`:

```bash
make install-api            # creates apps/api/.venv and installs the package + dev tools
make lint typecheck test    # ruff, mypy, pytest
```

Run the API locally (settings come from the environment; see `.env.example`):

```bash
cd apps/api
set -a && source ../../.env && set +a
.venv/bin/gunicorn --bind 127.0.0.1:8000 mediease_api.wsgi:app
curl -i localhost:8000/health
```

`make migrate` arrives in M0-P3.
