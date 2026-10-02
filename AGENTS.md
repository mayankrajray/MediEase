# AGENTS.md — Operating Instructions for AI Coding Agents

Tool-agnostic instructions for any AI agent (Claude Code, Codex, Cursor, Copilot, Gemini) working in
this repository. `CLAUDE.md` imports this file and adds the engineering principles. If the two ever
disagree, `CLAUDE.md` wins and this file must be corrected.

---

## 1. Read these first

| Order | File | Why |
|---|---|---|
| 1 | `TASKS.md` | Which milestone and phase is active. **Only work on the active phase.** |
| 1a | `NEXT_STEPS_PLAN.md` | Approved plan for the current milestone, workflow prerequisites and progress log |
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
| Version control | Git, GitHub, trunk-based; one branch and one PR per milestone; GitHub Actions CI | ADR-0001, ADR-0011 |

Exact library versions are pinned in `apps/api/pyproject.toml` and `apps/web/package.json`
(created in Milestone 0). Do not add a dependency without stating why in the change description.

---

## 3. Repository map

```
mediease/
├── AGENTS.md / CLAUDE.md / TASKS.md / SPECS.md   ← agent + planning files (root)
├── NEXT_STEPS_PLAN.md      ← approved plan for the active milestone + progress log
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
| `make up` | Build images and start the whole local stack with one command (`db` → `migrate` → `api` → `web` via `depends_on`; runs `docker compose up -d --wait --build`) | now |
| `make smoke` | End-to-end check of the running stack, including non-root / read-only / no capabilities (also a CI job) | now |
| `make audit` | Known-vulnerability check of API (pip-audit) and web (npm audit) dependencies | now |
| `make down` | Stop the stack | now |
| `make ps` / `make logs` | Service status / follow logs | now |
| `make psql` | Open a psql shell on the local database | now |
| `make install-api` | Create `apps/api/.venv` (Python 3.12) and install the API with dev tools | now |
| `make migrate` | Re-run Alembic migrations as a one-off container (`make up` already runs them) | now |
| `make test` | API + web test suites (API with the ≥ 90% package and ≥ 80% `domain/` + `application/` coverage gates) | now |
| `make test-api` / `make test-web` | One side only (`test-api` needs the db: `make up`) | now |
| `make lint` / `make typecheck` | Ruff + layer boundaries (import-linter) + mypy; ESLint + tsc | now |
| `make install-web` | `npm ci` in `apps/web` (Node from `apps/web/.nvmrc`, installed in WSL on Windows) | now |
| `make dev-web` | Next.js dev server on :3000 proxying to the API on localhost (`make up` first) | now |
| `make contract` / `make contract-check` | Regenerate web types from `contracts/openapi.yaml` / fail if the committed types are stale | now |
| `make seed` | Load generated (never real) demo data | M1 |
| `make worker` | Run the job worker in the foreground | M5 |

Verification before declaring a phase done: `make lint typecheck test` must pass. API tests include
real-PostgreSQL integration tests, so start the database first (`make up`); `make test-api` points
them at it through `TEST_DATABASE_URL`.

`make up` uses `--wait` with the one-off `migrate` service: verified on Compose v5.5.0 (M0-P3, and
again in M0-P5 with `web`) that it waits for `migrate` to exit 0 and for `api` and `web` to be
healthy, and exits 0.

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
- **Commits:** one commit per logical change; Conventional Commits subject in imperative mood with
  requirement IDs, plus a body explaining what and why, and `Refs #<milestone issue>` (CLAUDE.md
  "Commit Standards").

---

## 7. Boundaries — never do these

- Never read, print or modify `.env` or any secret file.
- Never use real patient data, real phone numbers or real clinic names in code, fixtures or docs.
- Never query a tenant table without the tenancy scope, and never add a "bypass" flag.
- Never put clinical content in logs, message bodies, analytics or error messages.
- Never generate medical advice, drug suggestions or dosage logic.
- Never run migrations inside application start-up.
- Never push to `origin/main`, never merge a PR, and never force-push or rewrite pushed history.
- Push only to the active milestone's branch, and only after the developer explicitly permits it.
- Never combine work from different milestones, or unrelated logic, in one branch, commit or PR
  (CLAUDE.md "Git Workflow", ADR-0011).
- Never start work on a milestone other than the active one in `TASKS.md`.
- Never disable, skip or loosen a test to make a build pass.

---

## 8. Output format for every change set

End each phase with:

1. **Summary** — what changed and why, with requirement IDs.
2. **Changed Files manifest** — added / modified / deleted.
3. **How to verify** — exact commands and expected output, including one failure path.
4. **Docs updated** — which of the files in CLAUDE.md's documentation table were touched.
5. **Commits and PR** — the list of logical commits (subject + body, per CLAUDE.md "Commit
   Standards"), the milestone issue, the milestone branch, and the milestone PR link once pushed
   with permission.
