# Migrations (Alembic)

Schema history for the MediEase database (ADR-0004). Config: `../alembic.ini`; environment:
`env.py`, which reads `DATABASE_URL` from the validated settings.

| Revision | What | Milestone |
|---|---|---|
| `0001` | Empty baseline — no tables | M0-P3 |
| `0002` | `clinics`, `users`, `clinic_memberships`, `doctors` | M1-P1 |
| `0003` | `users` credentials + lockout; `refresh_tokens` | M1-P2 |

## Running

- `make up` runs `alembic upgrade head` in the one-off `migrate` container before the API
  starts. `make migrate` re-runs it.
- From `apps/api` in the venv: `.venv/bin/alembic current`, `.venv/bin/alembic history`.
  Outside compose, the database host is `localhost`, not `db`.

## Adding a revision

1. Change the models in `src/mediease_api/adapters/db/models/`, then
   `alembic revision --rev-id 0004 -m "add audit events"` — revisions are numbered, not hashed.
   `--autogenerate` may draft it; review every line and spell enum values out instead of importing
   them, so the revision never changes when the code does.
2. Write `upgrade()` and `downgrade()`; follow expand → migrate → contract so the previous app
   version keeps working.
3. Update `docs/DATA_MODEL.md` in the same change; `test_models_match_migrations` fails until the
   models and the migrations agree.
4. Never edit a revision that has run anywhere shared; add a new one.
