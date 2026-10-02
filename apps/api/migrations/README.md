# Migrations (Alembic)

Schema history for the MediEase database (ADR-0004). Config: `../alembic.ini`; environment:
`env.py`, which reads `DATABASE_URL` from the validated settings.

| Revision | What | Milestone |
|---|---|---|
| `0001` | Empty baseline — no tables | M0-P3 |

## Running

- `make up` runs `alembic upgrade head` in the one-off `migrate` container before the API
  starts. `make migrate` re-runs it.
- From `apps/api` in the venv: `.venv/bin/alembic current`, `.venv/bin/alembic history`.
  Outside compose, the database host is `localhost`, not `db`.

## Adding a revision

1. `alembic revision --rev-id 0002 -m "add clinics"` — revisions are numbered, not hashed.
2. Write `upgrade()` and `downgrade()`; follow expand → migrate → contract so the previous app
   version keeps working.
3. Update `docs/DATA_MODEL.md` in the same change.
4. Never edit a revision that has run anywhere shared; add a new one.
