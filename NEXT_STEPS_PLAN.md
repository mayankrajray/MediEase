# NEXT_STEPS_PLAN.md — Approved plan for M1 (Identity, tenancy and audit)

| Field | Value |
|---|---|
| Status | M1 spec and design approved by the developer on 2 Oct 2026 |
| Scope | Milestone 1 in phase detail; M2–M6 as a roadmap only. The M0 plan is in git history (closed 2 Oct 2026, PRs #5–#15) |
| Live status | `TASKS.md` is authoritative for what is active. This plan is updated in the same PR as any change to scope, order or approach |
| Design notes | `docs/milestones/M1-identity-tenancy-audit.md` |
| Workflow rules | `CLAUDE.md` → "Git Workflow"; `CONTRIBUTING.md`; ADR-0010, ADR-0011 |

---

## 1. Problem statement

M0 delivered the foundation (typed settings, logging, `/health`, `/ready`, migrations, web shell,
hardened containers, CI gates) but no product behaviour. Every later milestone needs to know *who*
is acting and *for which clinic*, and must be unable to leak one clinic's data to another. M1
builds identity, tenancy and audit (PRD §8.1, FR-AUD) so M2 can register patients safely.

## 2. Requirements

- Spec: `docs/specs/identity-and-tenancy.md` (Approved). Its acceptance criteria AC1–AC6 become
  tests in the phase that implements them.
- **M1 exit:** an ops user onboards a clinic with an owner, doctor and front desk; each signs in
  and sees only their clinic; the tenancy test suite proves isolation.
- Follow `CLAUDE.md`: one phase at a time, design approved before code, `make lint typecheck test`
  green and the developer's confirmation before the next phase.
- NFR-14 from M1-P1: ≥ 80% coverage on `domain/` + `application/` (the ≥ 90% whole-package gate
  from M0 stays).
- Local resources: the WSL VM runs at its 8 GB limit; run `make down` whenever the stack is not in
  use.

## 3. Delivery workflow (ADR-0011)

```
Milestone issue #19 → branch m1/19-identity-tenancy-audit (from origin/main)
  → per phase: design → approval → logical commits → make lint typecheck test
    → developer confirms → push (with permission) to the same branch
  → one PR for the milestone: draft until P6 is done and the exit criteria hold
  → CI green → review + CODEOWNERS approval → maintainer rebase-merges
```

- Every commit has a Conventional Commits subject, a body (what + why) and `Refs #19`; the last
  commit of M1 carries `Closes #19`.
- Agents never push to `main`, push to the milestone branch only with permission, and never merge.

### 3.1 Open prerequisites

| # | Needed | State |
|---|---|---|
| W-5 | Branch protection / CODEOWNERS enforcement on `main` | **Open:** not available for a private repo on GitHub Free (HTTP 403). Needs GitHub Pro/Team or a public repo |
| — | `@akhtarjamal10` write access, so their CODEOWNERS entry takes effect | Open |
| — | Dependabot PRs #16–#18 (web toolchain majors) | Open; outside M1, reviewed separately |

## 4. Phase breakdown

Details, file lists and test plans per phase are in the design notes. Each phase is designed with
`/plan-phase` at its start; only P1 is designed in full now.

| Phase | Objective | Requirements | Verify |
|---|---|---|---|
| P1 | Domain model (Clinic, User, ClinicMembership, Doctor, Role), migration `0002`, tenancy-scoped repository base, unit of work, UUIDv7 IDs, coverage gate on `domain/` + `application/` | FR-ORG-01..03 (model), NFR-08, NFR-14; spec I1–I3, R9 (domain rule) | `make lint typecheck test`; `make up` applies `0002`; tenancy tests prove scoped repositories cannot reach another clinic |
| P2 | Argon2id hashing, sign-in (email or phone), refresh rotation with family revocation, sign-out, lockout | FR-AUTH-01, 02, 04; R1–R5; AC1, AC2 | Sign-in/refresh/sign-out via `curl`; lockout after 5 failures returns 423 |
| P3 | Access policy on every route (default deny) → `RequestContext`; session, user and membership re-checked per request; clinic resolution; permission matrix; `GET /api/v1/me` and read-only clinic endpoints (clinic, doctors, staff) | FR-AUTH-03, FR-ORG-04 (next request), NFR-08; R6–R8, R10; AC3, AC4 | Cross-clinic request → 404; deactivated user → `AUTH_ACCOUNT_DISABLED`; front desk on staff list → `PERM_DENIED` |
| P4 | Append-only audit events in the same transaction; database-enforced immutability (triggers, with a least-privilege role in M6-P1); `v_clinic_activity`; the audited staff role change | FR-AUD-01, 02; R11; AC5, AC6 | Role change writes one `staff.role_changed`; `UPDATE audit_events` refused |
| P5 | Ops API: create clinic → doctors → owner invite; owner staff and doctor management (invite, deactivate); onboarding checklist | FR-OPS-01, 04, FR-ORG-01..04; R9, R12 | Onboard a clinic end to end through the API; last owner cannot be demoted |
| P6 | Web: sign-in, clinic switcher, empty dashboard shell | FR-AUTH-01, R6; spec §6 | Sign in as each role in the browser; switcher only for multi-clinic users |

## 5. Roadmap after M1 (one line each)

- **M2 Patients** — registration, duplicate-phone flow, consent, CSV import, search
  (p95 < 500 ms at 10k patients). Needs `patients.md` `Approved`.
- **M3 Appointments and queue** — schedules, concurrency-safe booking, queue state machine,
  ETag polling.
- **M4 Visits and prescriptions** — immutable versioned Rx, PDF, signed patient links, bilingual
  360-px page.
- **M5 Messaging and reminders** — job table + worker, WhatsApp adapter + webhooks, reminder rules,
  STOP opt-out.
- **M6 Pilot hardening** — India-region deployment, backups + restore drill, security review,
  two pilot clinics.

## 6. Parallel non-code track

L-01 (Meta Business + WhatsApp number) and L-02 (template approval) are on the critical path for
M5; L-03, L-05 and L-07 should be under way. Details in `TASKS.md`.

## 7. Progress log

| Date | Task | Issue / PR | State |
|---|---|---|---|
| 1–2 Oct 2026 | M0 — Foundation (Tasks 0–6: workflow, db stack, API settings/logging/health, readiness + migrations, web shell, hardened images + CI) | #4–#14 / PRs #5, #7, #9, #11, #13, #15 | Merged; exit criteria met |
| 2 Oct 2026 | Workflow change: one issue, branch and PR per milestone (ADR-0011) | #19 | Committed on `m1/19-identity-tenancy-audit` |
| 2 Oct 2026 | `identity-and-tenancy.md` Approved; M1 plan and design notes | #19 | Committed on `m1/19-identity-tenancy-audit` |
| 2 Oct 2026 | M1-P1 — domain model, ports, UUIDv7, migration `0002`, tenancy-scoped repositories + unit of work, core coverage gate. `make lint typecheck test` green (API 166 tests, package 98%, core 100%); `make up` applies `0002` | #19 / PR #20 | Done; confirmed by the developer 3 Oct 2026 |
| 3 Oct 2026 | M1-P2 design (sign-in, refresh rotation, sign-out, lockout) approved | #19 / PR #20 | Done |
| 3 Oct 2026 | M1-P2 — Argon2id, JWT access + rotating refresh tokens with family revocation, CSRF double submit, lockout, migration `0003`, auth endpoints + contract, `make seed`. `make lint typecheck test` green (API 275 tests, package 99%, core 100%; web 32); on compose: `0003` applied, seed, curl sign-in by email and phone 200, AC1 423 + `Retry-After`, AC2 replay 401 `AUTH_REFRESH_REUSED` and newer token 401, sign-out 204 | #19 / PR #20 | Done; confirmed by the developer 3 Oct 2026 (sign-in on their machine: 200, cookie flags as designed) |
| 3 Oct 2026 | M1-P3 design (authorisation on every route) proposed | #19 / PR #20 | Approved by the developer 3 Oct 2026 |
| 3 Oct 2026 | M1-P3 — access policy on every route (default deny, start-up check), per-request re-check of session/user/membership, clinic resolution with `X-Clinic-ID`, PRD §8.1 permission matrix as domain data, `GET /api/v1/me` and read-only clinic/doctors/staff endpoints, contract 0.3.0 + regenerated web types, HTTP tenancy suite with a cross-clinic guard. `make lint typecheck test` green (API 389 tests, package 99%, core 99%; web 32); on compose with `make seed`: desk `/me` 200 and `/clinic/staff` 403 `PERM_DENIED`, owner `/clinic/staff` 200, own doctor 200 and another clinic's doctor 404 `REQ_NOT_FOUND`, ops `/me` 200 but `/clinic` 403, anonymous 401, and the old `me_access` after sign-out 401. Pushed to `m1/19-identity-tenancy-audit`; CI green (7/7 jobs); PR #20 body updated | #19 / PR #20 | Implemented; awaiting the developer's confirmation |
| 3 Oct 2026 | M1-P4 design (append-only audit log in the same transaction, database-enforced immutability, `v_clinic_activity`) proposed, with one open choice: whether the staff role change moves into P4 so AC5 is proved there (recommended) or stays in P5 | #19 / PR #20 | Approved by the developer 3 Oct 2026, option B (role change in P4) |
| 3 Oct 2026 | M1-P4 — `audit_events` + migration `0004` with two triggers that refuse UPDATE/DELETE/TRUNCATE (AC6), `AuditWriter` on the unit of work so a change is never unaudited (R11), session events + the audited `PATCH /clinic/staff/{id}` role change (AC5), `AUDIT_IP_SALT` and HMAC IP fingerprints, `v_clinic_activity`, contract 0.4.0 + regenerated web types, RUNBOOK §18. `make lint typecheck test` green (API 452 tests, package 99%, core 99%; web 32) | #19 / PR #20 | Implemented; awaiting the developer's confirmation |
