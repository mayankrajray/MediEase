# apps/api — MediEase API and worker

Flask API (HTTP + webhooks) and the background worker, sharing one hexagonal Python package.
Architecture: `docs/ARCHITECTURE.md` §3. Rules for agents: `CLAUDE.md` in this folder.

## Status

M0-P3: package, typed settings, structured logging, request IDs, error envelope, `GET /health`,
`GET /ready` (database check), Alembic with an empty baseline, and a minimal `Dockerfile` used by
the compose `migrate` and `api` services. The image is hardened in M0-P5
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
make up                     # db -> migrate -> api in containers; API on localhost:8000
make install-api            # creates apps/api/.venv and installs the package + dev tools
make lint typecheck test    # ruff, mypy, pytest (integration tests use the compose db)
make migrate                # re-run migrations (make up already ran them)
```

To run the API outside a container, point `DATABASE_URL` at `localhost` instead of `db`:

```bash
cd apps/api
set -a && source ../../.env && set +a
export DATABASE_URL="${DATABASE_URL/@db:/@localhost:}"
.venv/bin/gunicorn --bind 127.0.0.1:8001 mediease_api.wsgi:app
curl -i localhost:8001/ready
```
