# MediEase

A WhatsApp-native clinic operating system for independent clinics with one to four doctors in
India: booking, a live daily queue, a searchable patient record, a digital prescription patients
can re-read, and follow-up reminders that actually arrive.

> **Status:** Milestone 0 (Foundation) and Milestone 1 (Identity, tenancy and audit) complete (M1
> merged in PR #20); Milestone 2 (Patients) complete (PR #22); Milestone 3 (Appointments and daily queue)
> implemented (P1-P5: schedules, booking, the live queue and its screens), awaiting review in PR #37. See [TASKS.md](TASKS.md).

---

## Why

Most small clinics run on personal WhatsApp, phone calls and paper. Appointments get lost,
records can't be found during a consultation, follow-ups depend on memory, and medicine
instructions are explained once and forgotten. Full product rationale and evidence:
[docs/PRD.md](docs/PRD.md).

## Quick start

Prerequisites: Docker (with Compose v2), GNU Make, Git. Node.js LTS and Python 3.12 are only needed
if you run tools outside containers.

```bash
git clone <repo-url> mediease && cd mediease
cp .env.example .env          # then fill in local values
make up                        # builds and starts db -> migrate -> api -> web
make ps                        # check status (migrate shows "exited (0)")
curl -i localhost:8000/ready   # API ready: database reachable
make psql                      # open a database shell
make down                      # stop (data volume is kept)
```

Running tests and linters needs Python 3.12 and Node 24 (`apps/web/.nvmrc`); on Windows install
both inside WSL. With the stack up: `make install-api install-web && make lint typecheck test`.
`make smoke` checks the running stack end to end; `make dev-web` runs the web app with hot reload.

| Service | URL |
|---|---|
| Web app | http://localhost:3000 (`/status`) |
| API | http://localhost:8000 (`/health`, `/ready`) |
| PostgreSQL | localhost:5432 |

## Documentation map

| I want to… | Read |
|---|---|
| Understand the product and requirements | [docs/PRD.md](docs/PRD.md) |
| Know what is being built right now | [TASKS.md](TASKS.md), [NEXT_STEPS_PLAN.md](NEXT_STEPS_PLAN.md) |
| Understand the system design | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| See the database design | [docs/DATA_MODEL.md](docs/DATA_MODEL.md) |
| See the API design | [docs/API.md](docs/API.md), [contracts/openapi.yaml](contracts/openapi.yaml) |
| Implement a feature | [SPECS.md](SPECS.md) → `docs/specs/` |
| Debug a problem | [docs/DEBUGGING.md](docs/DEBUGGING.md), [docs/ERRORS.md](docs/ERRORS.md), [docs/DEBUG_JOURNAL.md](docs/DEBUG_JOURNAL.md) |
| Operate production | [docs/RUNBOOK.md](docs/RUNBOOK.md) |
| Handle data safely | [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md), [SECURITY.md](SECURITY.md) |
| Know why a decision was made | [docs/adr/](docs/adr/) |
| Work with an AI agent here | [CLAUDE.md](CLAUDE.md), [AGENTS.md](AGENTS.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Tech stack

Next.js + TypeScript · Flask (Python 3.12) · PostgreSQL · SQLAlchemy + Alembic · Docker Compose ·
GitHub Actions · WhatsApp Business Platform. Reasons are recorded in [docs/adr/](docs/adr/).

## Licence

Proprietary. All rights reserved.
