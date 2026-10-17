# Migrations (Alembic)

Schema history for the MediEase database (ADR-0004). Config: `../alembic.ini`; environment:
`env.py`, which reads `DATABASE_URL` from the validated settings.

| Revision | What | Milestone |
|---|---|---|
| `0001` | Empty baseline — no tables | M0-P3 |
| `0002` | `clinics`, `users`, `clinic_memberships`, `doctors` | M1-P1 |
| `0003` | `users` credentials + lockout; `refresh_tokens` | M1-P2 |
| `0004` | `audit_events` with append-only triggers; `v_clinic_activity` | M1-P4 |
| `0005` | `clinic_memberships` invitation columns; `onboarding_checklists` | M1-P5 |
| `0006` | `clinics.patient_code_prefix` and `next_patient_seq`; `patients` table with lookup indexes | M2-P1 |
| `0007` | `clinics.booking_mode`; `doctor_schedules`, `schedule_exceptions`, `sessions` | M3-P1 |
| `0008` | `appointments` (partial unique indexes back the booking rules), `appointment_status_history` | M3-P2 |

## Running

- `make up` runs `alembic upgrade head` in the one-off `migrate` container before the API
  starts. `make migrate` re-runs it.
- From `apps/api` in the venv: `.venv/bin/alembic current`, `.venv/bin/alembic history`.
  Outside compose, the database host is `localhost`, not `db`.

## Adding a revision

1. Change the models in `src/mediease_api/adapters/db/models/`, then
   `alembic revision --rev-id 0008 -m "add appointments"` — revisions are numbered, not hashed.
   `--autogenerate` may draft it; review every line and spell enum values out instead of importing
   them, so the revision never changes when the code does.
2. Write `upgrade()` and `downgrade()`; follow expand → migrate → contract so the previous app
   version keeps working.
3. Update `docs/DATA_MODEL.md` in the same change; `test_models_match_migrations` fails until the
   models and the migrations agree.
4. Never edit a revision that has run anywhere shared; add a new one.
