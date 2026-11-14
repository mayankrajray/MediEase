# Spec: Ops clinic usage

| Field | Value |
|---|---|
| Requirements | FR-OPS-03 (clinic health view: last login, appointments, prescriptions, reminders sent/failed; no clinical content) |
| Milestone / phases | M9 / P4 (design `docs/milestones/M9-deploy-demo.md` §10) |
| Status | Implemented 14 Nov 2026 |
| Owner | Developer |
| Last updated | 2026-11-14 |

## 1. Context
The pilot scorecard and the Phase 2 submission need evidence that each clinic actually uses
MediEase: who signed in, and how many patients, appointments, visits, prescriptions and bills it
recorded each week. Until now ops could only see the onboarding checklist. This view gives that
evidence as counts, and a CSV of it, without showing any patient or clinical detail.

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Ops admin (`OPS_ADMIN`) | Read every clinic's usage counts; download them as CSV | See any patient, visit, prescription or message content |
| Clinic staff (any role) | — | Read this view (403) |

## 3. Domain model
No new table. A cross-clinic read model (`ClinicUsageReport`, adapter
`SqlAlchemyClinicUsageReport`), a reviewed exception to the tenancy scoping in the same way as
`SqlAlchemyMessageCostReport` (`tests/tenancy/test_repository_scoping.py`).

## 4. Behaviour
- **R1** `GET /api/v1/ops/clinic-usage?weeks=N` returns the last N weeks (1–12, default 4), oldest
  first. Weeks run Monday to Sunday in India time; the current week is included, partly done.
- **R2** Counts, dates and clinic names only. Per week and in total since the clinic began:
  patients (by `created_at`), appointments not cancelled (by `created_at`), visits (by
  `started_at`), prescriptions (by `issued_at`) and bills (`kind = BILL`, by `issued_at`). A
  record is placed in a week by the clinic's own timezone.
- **R3** People: owners, doctors (active doctor profiles, so a practising owner counts), front
  desk, distinct active members, and members active in the last 7 days (signed in, or an audit
  event in the clinic).
- **R4** Last active is the latest of a sign-in, an audit event or a record. "Active this week"
  means a member signed in or worked in the last 7 days, or a record was made this week.
- **R5** Delivery health in the last 7 days: failed messages (excluding
  `MSG_CHANNEL_DISABLED`, which are counted apart as "not sent") and dead jobs. No message body
  or recipient is returned.
- **R6** The response has a summary: clinic count, clinics active this week (R4), and totals
  per metric across the weeks shown.

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/ops/clinic-usage` | `weeks` 1–12 (default 4) | 200 `OpsClinicUsage` | 401; 403 for non-ops; 422 when `weeks` is outside 1–12 |

## 6. UI notes
`/ops/usage`, "Clinic usage" in the ops navigation.
- Header with 4 / 8 / 12 weeks, Refresh and *Download CSV* (all clinics).
- A summary strip: clinics active, patients, appointments, visits, prescriptions.
- One row per clinic, active first: name and status, last active, people, a bar per week of visits
  (with the numbers as text for screen readers), prescriptions, delivery health, *Details*.
- *Details* opens the clinic's week-by-week table with an "All time" line and a per-clinic CSV.
- Loading skeleton; empty state with *Create clinic*; error notice with *Try again*.
- On phones the table becomes cards (`me-table`).

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| Reading the view | — (read only, counts only) | — | — |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| A clinic with no records | Row shows "Not used yet", zeros, "Setting up" status |
| Messaging disabled on the deployment | Not-sent messages counted apart, not as failures |
| A clinic in another timezone | Its records are bucketed in its own zone; week starts follow India time |
| `weeks=0`, `13` or text | 422 |

## 9. Acceptance criteria
- **AC1 (FR-OPS-03)** Given the bundled demo clinic, when ops read the view, then the totals are
  20 patients, 36 appointments, 26 visits, 24 prescriptions and 26 bills, with 4 members.
- **AC2 (FR-OPS-03)** Given `weeks=1` or `weeks=12`, then that many weeks are returned; `weeks=13`
  returns 422.
- **AC3 (FR-OPS-03)** Given a clinic owner, when they call the endpoint, then 403.
- **AC4** The response matches `contracts/openapi.yaml` (`OpsClinicUsage`).
- **AC5** The page lists active clinics first, opens a clinic's weeks with an all-time line, and
  writes the CSV with one line per week and an all-time line.

## 10. Observability
Standard request log only; no new error codes.

## 11. Out of scope
Charts over months, per-doctor usage, alerting on inactivity, server-side CSV.

## 12. Open questions
None.
