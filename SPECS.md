# SPECS.md — Specification Index and Format

A **spec** turns PRD requirements into behaviour precise enough to implement and test without
guessing. The PRD says *what and why*; a spec says *exactly how it behaves*; the code says *how it
is built*. Specs live in `docs/specs/`, one file per feature.

Rule: **no behaviour-changing code without an approved spec.** If implementation reveals the spec is
wrong, update the spec first, then the code.

---

## Index

| Spec | Requirements | Milestone | Status |
|---|---|---|---|
| [identity-and-tenancy.md](docs/specs/identity-and-tenancy.md) | FR-ORG, FR-AUTH, FR-AUD | M1 | Approved |
| [patients.md](docs/specs/patients.md) | FR-PAT | M2 | Implemented |
| [appointments-and-queue.md](docs/specs/appointments-and-queue.md) | FR-APT, FR-QUE | M3 | Draft |
| [prescriptions.md](docs/specs/prescriptions.md) | FR-VIS, FR-RX | M4 | Draft |
| [reminders-and-messaging.md](docs/specs/reminders-and-messaging.md) | FR-REM, FR-MSG | M5 | Draft |
| Public booking page | FR-PUB | M7 | Not started |

Status values: `Not started` → `Draft` → `Approved` (developer sign-off; implementation may begin)
→ `Implemented` (all acceptance criteria have passing tests) → `Superseded`.

---

## Spec format

Copy [`docs/specs/_TEMPLATE.md`](docs/specs/_TEMPLATE.md). Every spec has these sections:

1. **Header** — requirement IDs, milestone, status, owner, last updated.
2. **Context** — the user problem in two or three sentences, linked to PRD evidence.
3. **Actors and permissions** — who can do what (refers to the PRD permission matrix).
4. **Domain model** — entities, fields, invariants, state machines (Mermaid `stateDiagram`).
5. **Behaviour** — numbered rules (`R1`, `R2`, …). Each rule is testable on its own.
6. **API surface** — endpoints, request/response shapes, error codes (must match `contracts/openapi.yaml`).
7. **UI notes** — screens, states (empty, loading, error), and the minimum interaction count.
8. **Events and side effects** — audit entries, jobs enqueued, messages sent, analytics events.
9. **Edge cases** — explicit list, each with the expected outcome.
10. **Acceptance criteria** — Given / When / Then, each tagged with a requirement ID. These become tests.
11. **Observability** — log events, metrics, and the error codes an operator will see.
12. **Out of scope** — what this spec deliberately does not cover.
13. **Open questions** — resolved before status becomes `Approved`.

---

## Writing rules

- Use **must** for required behaviour and **may** for optional behaviour. Avoid "should".
- Every rule is observable from outside the unit (API response, database row, message, log event).
- Numbers are concrete: limits, timeouts, retries, sizes, time windows, time zones.
- Name error codes in the spec; add them to `docs/ERRORS.md` when implemented.
- No clinical logic. If a rule sounds like medical advice, it does not belong in MediEase.
- Keep examples synthetic — invented names, `+91 90000 000xx` style numbers.

## Using specs with AI agents

Prompt pattern for a phase:

> Read `TASKS.md`, then `docs/specs/<spec>.md` rules R1–R6 for phase M3-P2. Explain the design and
> list the files you will change. Wait for approval before writing code.

The acceptance criteria are the contract: an agent's phase is complete when each criterion has a
test that passes and the manifest lists it.
