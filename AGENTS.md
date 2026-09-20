# AGENTS.md — Operating Instructions for AI Coding Agents

Tool-agnostic instructions for any AI agent (Claude Code, Codex, Cursor, Copilot, Gemini) working in
this repository. `CLAUDE.md` imports this file and adds the engineering principles. If the two ever
disagree, `CLAUDE.md` wins and this file must be corrected.

---

## 1. Read these first

| Order | File | Why |
|---|---|---|
| 1 | `TASKS.md` | Which milestone and phase is active. **Only work on the active phase.** |
| 2 | `docs/specs/<feature>.md` for that phase | Acceptance criteria you must satisfy |
| 3 | `docs/PRD.md` | Requirement IDs and product intent |
| 4 | `docs/ARCHITECTURE.md` | Layers, request flow, where code goes |
| 5 | `docs/DEBUGGING.md` + `docs/DEBUG_JOURNAL.md` | Before investigating any failure |

---

## 2. Stack

| Concern | Choice | Decision record |
|---|---|---|
| Web app | Next.js (App Router) + TypeScript, Tailwind CSS | ADR-0002 |
| API | Python 3.12, Flask (app factory), Pydantic v2 for validation and settings | ADR-0002 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.x (Core + ORM), Alembic migrations | ADR-0004 |
| Background work | PostgreSQL-backed job table + a separate worker process | ADR-0005 |
| Multi-tenancy | Shared schema, `clinic_id` on every tenant row, scoped repositories | ADR-0003 |
| Auth | Argon2id passwords, JWT access + rotating refresh in HttpOnly cookies | ADR-0006 |
| Messaging | WhatsApp Business Platform (Cloud API) + SMS behind a `MessagingPort` | ADR-0007 |
| Contract | OpenAPI 3.1 in `contracts/openapi.yaml`; web types generated from it | ADR-0008 |
| Runtime | Docker + Docker Compose locally; single-region India deployment for pilot | ADR-0009 |
| Version control | Git, GitHub, trunk-based with short-lived branches, GitHub Actions CI | ADR-0001 |

Exact library versions are pinned in `apps/api/pyproject.toml` and `apps/web/package.json`
(created in Milestone 0). Do not add a dependency without stating why in the change description.

---

## 3. Repository map

```
mediease/
├── AGENTS.md / CLAUDE.md / TASKS.md / SPECS.md   ← agent + planning files (root)
├── README.md / CONTRIBUTING.md / SECURITY.md / CHANGELOG.md
├── .env.example            ← every setting, documented; copy to .env
├── docker-compose.yml      ← services that exist *today*
├── Makefile                ← the only commands humans and agents should need
├── contracts/openapi.yaml  ← HTTP contract (source of truth for web types)
├── apps/
│   ├── api/                ← Flask API + worker (hexagonal)
│   │   ├── CLAUDE.md       ← API-specific rules (loaded when working in apps/api)
│   │   ├── src/mediease_api/
│   │   │   ├── domain/         entities, value objects, domain errors — no framework imports
│   │   │   ├── application/    use cases; depend only on domain + ports
│   │   │   ├── ports/          interfaces: repositories, messaging, clock, storage, pdf
│   │   │   ├── adapters/       SQLAlchemy repos, WhatsApp/SMS/console, S3/local storage, PDF
│   │   │   ├── delivery/       http (Flask blueprints), webhooks, worker entrypoint
│   │   │   ├── config/         typed settings, logging setup
│   │   │   └── bootstrap.py    composition root (created in M0)
│   │   ├── migrations/     Alembic
│   │   └── tests/          unit/ integration/ contract/ tenancy/
│   └── web/                ← Next.js app
│       ├── CLAUDE.md
│       └── src/
│           ├── app/(clinic)/   authenticated clinic dashboard
│           ├── app/(patient)/  public patient pages (prescription link, booking page)
│           ├── app/(ops)/      internal ops console
│           ├── features/       feature modules (appointments, queue, patients, rx…)
│           ├── components/     shared UI primitives
│           └── lib/            api client (generated types), auth, formatting, i18n
├── docs/
│   ├── PRD.md  ARCHITECTURE.md  DATA_MODEL.md  API.md
│   ├── DEBUGGING.md  ERRORS.md  DEBUG_JOURNAL.md  RUNBOOK.md
│   ├── SECURITY_AND_COMPLIANCE.md  TESTING.md  GLOSSARY.md
│   ├── adr/           architecture decision records
│   ├── specs/         one spec per feature (format in SPECS.md)
│   └── milestones/    design notes for the active and completed milestones
├── infra/             deployment config (reserved until M6)
├── scripts/           one-off operational scripts (seed, anonymised fixtures)
├── .claude/           Claude Code settings and slash commands
└── .github/           CI workflows, PR and issue templates
```

---

## 4. Commands

Run everything through `make`. Targets marked *M0* are added during Milestone 0; until then they
do not exist.

| Command | What it does | Available |
|---|---|---|
| `make help` | List targets | now |
| `make up` | Start the local stack | now (database only), full stack from M0 |
| `make down` | Stop the stack | now |
| `make ps` / `make logs` | Service status / follow logs | now |
| `make psql` | Open a psql shell on the local database | now |
| `make migrate` | Run Alembic migrations as a one-off container | M0 |
| `make test` | API + web test suites | M0 |
| `make test-api` / `make test-web` | One side only | M0 |
| `make lint` / `make typecheck` | Ruff + mypy; ESLint + tsc | M0 |
| `make contract` | Validate `openapi.yaml` and regenerate web types | M0 |
| `make seed` | Load generated (never real) demo data | M1 |
| `make worker` | Run the job worker in the foreground | M5 |

Verification before declaring a phase done: `make lint typecheck test` must pass.

---

## 5. Where does new code go?

| You are adding… | Put it in… |
|---|---|
| A business rule ("a slot cannot be double-booked") | `domain/` |
| A user action ("book appointment") | `application/<feature>/` as a use case |
| A new external dependency (provider, storage) | a port in `ports/`, an adapter in `adapters/`, wired in `bootstrap.py` |
| An HTTP endpoint | `delivery/http/<feature>.py` + `contracts/openapi.yaml` |
| A webhook | `delivery/webhooks/` (verify signature first, then enqueue) |
| A scheduled or background action | a job handler in `application/jobs/`, registered with the worker |
| A table change | model in `adapters/db/models/` + Alembic migration + `docs/DATA_MODEL.md` |
| A clinic screen | `apps/web/src/app/(clinic)/…` using a module from `features/` |
| A patient-facing page | `apps/web/src/app/(patient)/…` — mobile-first, no login, < 200 KB |
| A new error | domain/application error class + `docs/ERRORS.md` entry |

---

## 6. Conventions

- **Python:** Ruff (lint + format), mypy strict for `domain/` and `application/`. Type hints
  everywhere. Use cases are classes with a single `execute()` method and injected ports.
- **TypeScript:** strict mode, ESLint, no `any`. Server Components by default; Client Components
  only for interactivity. Data fetching through `lib/api` only.
- **Naming:** snake_case in Python and the database; camelCase in TypeScript; kebab-case URLs;
  JSON payloads use snake_case (the generated client maps types, not casing).
- **IDs:** UUIDv7 primary keys; human-readable clinic-scoped codes (`ME-0142`) are separate columns.
- **Money:** integer paise. **Time:** `timestamptz` in UTC; clinic timezone applied at the edge.
- **Phones:** E.164, validated and normalised at the boundary; masked in logs.
- **Errors:** raise domain/application errors with a stable `code`; the HTTP layer maps them.
- **Tests:** name the requirement, e.g. `test_fr_apt_04_concurrent_booking_one_wins`.
- **Commits:** Conventional Commits with requirement IDs.

---

## 7. Boundaries — never do these

- Never read, print or modify `.env` or any secret file.
- Never use real patient data, real phone numbers or real clinic names in code, fixtures or docs.
- Never query a tenant table without the tenancy scope, and never add a "bypass" flag.
- Never put clinical content in logs, message bodies, analytics or error messages.
- Never generate medical advice, drug suggestions or dosage logic.
- Never run migrations inside application start-up.
- Never commit, push, merge, rebase or force anything unless the developer asks.
- Never start work on a milestone other than the active one in `TASKS.md`.
- Never disable, skip or loosen a test to make a build pass.

---

## 8. Output format for every change set

End each phase with:

1. **Summary** — what changed and why, with requirement IDs.
2. **Changed Files manifest** — added / modified / deleted.
3. **How to verify** — exact commands and expected output, including one failure path.
4. **Docs updated** — which of the files in CLAUDE.md's documentation table were touched.
5. **Suggested commit message** — Conventional Commit format.
