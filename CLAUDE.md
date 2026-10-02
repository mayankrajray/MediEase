# CLAUDE.md — Engineering Guide for MediEase

This document defines **how we build** MediEase. It captures durable engineering principles and
working agreements, not implementation details. It must remain valid across every milestone.
Anything version-specific, milestone-specific or temporary belongs in `docs/ARCHITECTURE.md`,
`docs/milestones/`, `TASKS.md` or the code — **not here**.

When generating or reviewing work in this repository, follow this guide unless the developer
explicitly approves a deviation.

Operational facts — commands, repository map, file-placement rules — live in `AGENTS.md` so every
AI tool reads the same source. It is imported here:

@AGENTS.md

---

## Project Purpose

MediEase is a WhatsApp-native clinic operating system for independent clinics with one to four
doctors in India: booking, a live daily queue, a searchable visit record, a digital prescription the
patient can re-read, and follow-up reminders that actually arrive.

It handles **patient health data**. Every decision is made as if a real clinic's patients depend on
it, because they will. The product is built to be long-lived and maintainable, not a one-off
prototype. The *why* and *what* are in `docs/PRD.md`; requirement IDs (`FR-…`, `NFR-…`) from that
document are the shared vocabulary for specs, tasks, tests and commits.

---

## Engineering Philosophy

- **Clarity over cleverness.** Code is read far more often than it is written. Prefer the obvious
  solution a new engineer can follow.
- **Small, reversible steps.** Build in increments that can be understood, tested and rolled back
  independently.
- **Production quality at every step.** Every file is fit for its current scope. No throwaway
  placeholders that are "fixed later".
- **The developer must understand the system.** Speed is secondary to comprehension. If a change
  cannot be explained, it is not ready.
- **Fail fast and loudly.** Misconfiguration and invalid state surface at startup or at the
  boundary, not deep inside a request.
- **Debuggability is a feature.** A bug that cannot be traced from a log line to a request to a
  record is a design defect, not bad luck.

---

## Safety Rules for Health Data (non-negotiable)

- **Tenancy is enforced in one place.** Every tenant-owned query goes through the tenancy-scoped
  repository layer. No handler, job or script queries tenant tables without a `clinic_id` scope.
- **Clinical content never leaves its boundary.** Diagnoses, notes, medicine names and instructions
  never appear in logs, error messages, analytics events, message bodies or test fixtures copied
  from real data. Messages carry links, not content.
- **No real patient data outside production.** Local, test and CI environments use generated
  fixtures only. Never paste production data into an AI tool, issue, PR or chat.
- **MediEase never produces clinical advice.** No drug, dose, interaction or diagnosis suggestions
  from code or from any model. Autocomplete draws only from the clinic's own history.
- **Issued prescriptions are immutable.** Corrections are new versions; history is never rewritten.
- **Audit what matters.** Every access or change listed in `FR-AUD-01` produces an append-only
  audit entry in the same transaction as the change.
- **Secrets stay in the environment.** Never read, print, commit or echo `.env` contents.

---

## Architecture Principles

- **Clean / Hexagonal architecture.** Dependencies point inward. The domain core has no knowledge
  of Flask, SQLAlchemy, HTTP, WhatsApp or any SDK.
- **Ports and adapters.** Anything that talks to the outside world — database, messaging providers,
  file storage, PDF rendering, clock, ID generation — sits behind a port with swappable adapters.
  Application logic depends on the port, never the adapter.
- **Single source of truth for configuration.** All configuration is loaded once into a typed,
  validated settings object. No module reads environment variables directly.
- **Separation of concerns.** Delivery (HTTP, webhooks, worker entrypoints), application (use
  cases), domain (entities, value objects, rules) and infrastructure (adapters) are distinct
  layers with clear boundaries.
- **Composition root.** Configuration, logging, dependencies and routes are wired in one explicit
  place (the Flask app factory and the worker entrypoint), with no import-time side effects.
- **Contract first.** The HTTP contract in `contracts/openapi.yaml` is updated in the same change as
  the endpoint. The web app's types are generated from it, never hand-copied.
- **Extensibility by data and registration.** New message templates, reminder types, specialty
  templates and channels are added by configuration or by registering an implementation — not by
  editing existing branching logic.
- **Time is explicit.** Store UTC; convert at the edge using the clinic's timezone. Inject a clock
  port instead of calling "now" inside domain logic.

---

## External Provider Integration

The application never depends directly on a specific provider. Messaging (WhatsApp Business
Platform, SMS gateways), storage, PDF generation and any future AI capability are reached through
ports. Concrete implementations live in the infrastructure layer and are replaceable without
touching application logic. Every provider has a local/dev adapter so the full stack runs without
external accounts.

Provider calls are **idempotent** (idempotency key per outbound message), **time-bounded**
(explicit timeouts), and **observable** (provider request ID logged against our `request_id`).

---

## Architecture Decisions

Significant decisions are recorded as ADRs in `docs/adr/` using `docs/adr/0000-template.md`.

Each ADR documents:

- Context
- Decision
- Alternatives considered
- Consequences

The goal is to preserve the reasoning behind a choice, not just the outcome. An ADR is never edited
after acceptance; it is superseded by a new ADR that links back to it.

---

## Documentation That Makes Debugging Possible

Documentation is part of the change, not an afterthought. A phase is not done until the documents
it affects are current.

| When you change… | Also update… |
|---|---|
| An endpoint or payload | `contracts/openapi.yaml`, `docs/API.md` |
| A table, column or index | Alembic migration, `docs/DATA_MODEL.md` |
| An error condition | `docs/ERRORS.md` (code, HTTP status, meaning, likely cause, where to look) |
| A background job or message template | `docs/specs/` for the feature, `docs/RUNBOOK.md` if operators act on it |
| Configuration | `.env.example` with a comment, the settings object, `AGENTS.md` if a command changes |
| An architectural choice | a new ADR |
| A bug you fixed | an entry in `docs/DEBUG_JOURNAL.md` (symptom → root cause → fix → prevention) |
| Milestone status | `TASKS.md` and `CHANGELOG.md` |
| Scope, order or approach of the active plan | `NEXT_STEPS_PLAN.md` (progress log included) |

**Before debugging anything, read `docs/DEBUGGING.md` and search `docs/DEBUG_JOURNAL.md`** — the
same failure may already be explained.

---

## Observability Standards

- **Structured logs only.** JSON, one event per line, with `timestamp`, `level`, `event`,
  `request_id`, `clinic_id`, `user_id` (internal IDs only), `route`, `duration_ms`.
- **One request, one ID.** The web app sends `X-Request-ID`; the API generates one if missing,
  returns it in the response, stores it on jobs it enqueues, and passes it to providers where
  possible. A single ID must trace a booking from click to WhatsApp delivery.
- **Log events, not prose.** `event="reminder.send_failed"` with fields, not
  `"something went wrong sending reminder"`.
- **Errors carry stable codes.** Every API error returns `{ "error": { "code", "message",
  "request_id", "details" } }`. Codes are catalogued in `docs/ERRORS.md`.
- **Levels mean something.** `ERROR` = needs a human; `WARNING` = degraded but handled; `INFO` =
  business event; `DEBUG` = off in production.
- **Never log PII or clinical content.** Phone numbers are masked (`+91******3210`); names,
  notes and prescriptions are never logged.

---

## Development Workflow

- **One milestone at a time.** Never generate multiple milestones at once, and never write code for
  a future milestone.
- **Phased rollout within a milestone.** Large milestones are split into small logical phases
  (see `TASKS.md`). Each phase is explained, implemented and tested before the next begins.
- **One issue per logical task.** Every task is tracked by a repository issue before work starts;
  the issue links the phase, requirement IDs and acceptance criteria.
- **Spec before code.** A phase that adds behaviour has a spec in `docs/specs/` (format in
  `SPECS.md`) with acceptance criteria tied to requirement IDs.
- **Explain before implementing.** Every phase starts with the design: what is being built, why,
  where it fits, and which files will change.
- **Approval gates.** Implementation proceeds only after the design is approved, and the next phase
  begins only after the current one is tested and confirmed by the developer.
- **The connected repository is the single source of truth.** Changes are surgical — only the files
  that must change are touched.
- **The plan stays in sync.** `NEXT_STEPS_PLAN.md` is updated in the same PR as any change to the
  agreed scope, order or approach.

---

## Code Generation Rules

- **Modify only what the current phase requires.** Do not rewrite unrelated files.
- **No placeholder or dead code.** Stubs are only acceptable when they are an intentional,
  documented part of a designed interface.
- **Keep changes reviewable.** Small, focused diffs over sweeping ones.
- **Follow the established structure.** New files go in the layer and folder that match their
  responsibility. Reserved folders (each with a `README.md`) signal where future work belongs.
- **Comment the "why", not the "what".** Explain intent and trade-offs.
- **Consistency over personal preference.** Match existing patterns, naming and style.
- **Reference requirement IDs.** Tests and use cases name the `FR-…`/`NFR-…` they satisfy.

---

## Docker / Service Architecture

- **Containerised and reproducible.** Every service runs in a container and the whole stack starts
  from one documented command (`make up`, a single `docker compose up`). No separate manual start-up
  steps.
- **Each running service must have a current purpose.** A service appears in `docker-compose.yml`
  only when the application actually uses it.
- **Health and readiness are first-class.** Services expose liveness (`/health`) and readiness
  (`/ready`, including dependencies). Dependents wait for readiness, not mere startup.
- **Start-up order is declared, not scripted.** Dependencies use Compose `depends_on` conditions:
  the migration service waits for the database to be `service_healthy`; the API waits for the
  database (`service_healthy`) and for the migration service (`service_completed_successfully`);
  the web app waits for the API (`service_healthy`).
- **Schema changes run as a discrete step.** Migrations run as their own one-off container, never
  inside the API process at boot.
- **Volumes are explicit and preserved.** Persistent data lives in named volumes declared in
  compose (e.g. `pgdata`); `make down` never removes them. Code and migrations are baked into
  images rather than bind-mounted outside local development.
- **Configuration and secrets come from the environment.** Nothing sensitive is baked into images
  or committed.
- **Least privilege.** Non-root users, minimal images, read-only filesystems where practical.

---

## Infrastructure Philosophy

- **Introduce technology only when a concrete feature requires it.** No caches, queues or external
  services in anticipation of need.
- **Justify every dependency.** A new library or service is added with a reason and a pinned
  version, recorded in the dependency file and, if significant, an ADR.
- **Prefer the smallest sufficient solution.** Reach for more infrastructure only after simpler
  options are genuinely outgrown (e.g. PostgreSQL-backed jobs before a message broker — ADR-0005).
- **Keep components swappable.** Because infrastructure lives behind ports, any piece can be
  replaced without rewriting application logic.

---

## Git Workflow

Every task follows the same path (ADR-0010):

```
Issue → task branch → implementation → logical commits → push (with permission) → PR
      → CI green → review + CODEOWNERS approval → merge by an authorised maintainer
```

- **One issue per logical task.** Each issue has exactly one branch and one PR. Unrelated tasks or
  logic are never combined in the same branch or PR.
- **Short-lived branches** named `m<milestone>/p<phase>-<issue#>-<slug>`, e.g.
  `m3/p2-41-token-queue`, created from the latest `origin/main`.
- **Never push to `origin/main`**, directly or by any other route. Work reaches `main` only through
  a reviewed PR.
- **Push only with permission.** Agents may create issues, branches and local commits for the
  active task. They push to the task branch and open the PR only after the developer explicitly
  permits it for that task.
- **Never merge.** Merging is done by an authorised maintainer after green CI and the required
  reviews, including CODEOWNERS approval where the repository enforces it. Merge method:
  **rebase and merge**, so logical commits are preserved with a linear history.
- **No history rewriting on shared branches.** No force push, `reset --hard` or rebase of a pushed
  branch without the developer's explicit approval.
- **Every change set ends with a Changed Files manifest** (added / modified / deleted) and the
  list of commits.
- **Build artifacts and secrets are never committed.**

---

## Commit Standards

- **One commit per logical change.** A commit does one thing that can be reviewed, tested and
  reverted on its own. Tests that prove a change travel with it. Never mix refactoring,
  formatting and behaviour changes in one commit.
- **Every commit builds and passes tests**, so `git bisect` works.
- **Subject line:** Conventional Commits prefix, imperative mood, ≤ 72 characters, no trailing
  period, requirement ID where one applies.
- **Blank line, then a body** wrapped at 72 characters explaining *what* changed and *why* — the
  problem, the approach, trade-offs or follow-ups. The diff shows *how*.
- **Footer:** `Refs #<issue>` on every commit; `Closes #<issue>` on the final commit of the PR.
  Add `BREAKING CHANGE:` when applicable.
- **Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `security`, `build`, `ci`.

Example:

```
feat(config): add typed settings with fail-fast validation (NFR-12)

All configuration is loaded once into AppSettings so no module reads
os.environ directly. Invalid or missing values stop the process at
start-up with config.invalid naming the field, instead of failing deep
inside a request.

Staging and production reject DEBUG logging, insecure cookies and
change-me placeholders.

Refs #4
```

---

## Teaching Expectations

- **Teach each new concept before using it** — dependency injection, repository pattern, ports and
  adapters, tenancy scoping, row locking, idempotency keys, outbox/job tables, signed URLs,
  webhook verification, migrations.
- **Explain the reasoning, not just the result**, including trade-offs and alternatives.
- **Use diagrams and request flows** where they make the design clearer (Mermaid in Markdown).
- **Optimise for the developer's understanding.** The goal is a developer who can explain every
  architectural decision and every file.

---

## Testing Expectations

- **Every phase is verifiable.** Each phase ends with explicit steps to run it, the expected
  output, and how to confirm success.
- **The developer tests before we advance.**
- **Test the failure paths.** Invalid input, missing permission, cross-tenant access, provider
  timeout and duplicate webhook are tested wherever they apply.
- **Tenancy isolation is a permanent test suite.** Every new tenant-owned resource adds a test that
  another clinic's user cannot read or modify it.
- **Verification grows with the system.** Prefer automated unit, integration and contract checks
  over manual steps. Details in `docs/TESTING.md`.
- **Readiness reflects truth.** Health checks accurately represent whether dependencies are usable.

---

## Debugging Protocol

When something is broken, follow this order and write down what you find:

1. **Reproduce** with the smallest input. Record the exact command, request and `request_id`.
2. **Locate** using `docs/DEBUGGING.md` (symptom → where to look) and search `docs/DEBUG_JOURNAL.md`.
3. **Read the evidence** — logs filtered by `request_id`, the error `code`, the job/message row —
   before forming a theory.
4. **State a hypothesis** and the observation that would disprove it.
5. **Fix the root cause**, not the symptom. Add a test that fails without the fix.
6. **Record it** in `docs/DEBUG_JOURNAL.md`; update `docs/ERRORS.md` or `docs/RUNBOOK.md` if a
   future operator would need the knowledge.

Never "fix" a failure by widening a permission, removing a tenancy scope, catching and ignoring an
exception, or disabling a test.

---

## Definition of Done

A milestone (or phase) is complete only when:

- An issue tracks the task, and its branch and PR contain only that task's changes.
- Architecture has been explained.
- A spec exists with acceptance criteria linked to requirement IDs.
- Code has been generated, and only required files were modified.
- Tests cover the happy path, failure paths and tenancy isolation where relevant.
- Documentation listed in "Documentation That Makes Debugging Possible" is updated.
- A Changed Files manifest and testing steps are provided.
- The developer has successfully tested the phase.
- `TASKS.md`, `CHANGELOG.md` and `NEXT_STEPS_PLAN.md` reflect the new state.
- Each logical change is its own commit following "Commit Standards".
- The branch is pushed (with permission), the PR is green, reviewed and CODEOWNERS-approved, and an
  authorised maintainer has merged it.
- Approval is received before the next milestone begins.
