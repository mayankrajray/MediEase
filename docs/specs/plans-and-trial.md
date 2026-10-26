# Spec: Plans, trial and limits

| Field | Value |
|---|---|
| Requirements | FR-SUB-01 |
| Milestone / phase | M6d / P7 (design: `docs/milestones/M6d-billing-and-documents.md`, decisions B9, D4, D5) |
| Status | Approved 26 Oct 2026 (P2–P7 in advance) and built |
| Owner | Developer |
| Last updated | 2026-10-26 |

## 1. Context
MediEase is sold per clinic in three plans that differ by how many doctors and people a clinic
may have (PRD §12). A new clinic gets 14 days free. P7 records each clinic's plan, starts the trial,
and enforces the limits on every path that adds or brings back a doctor or a member. There is no
payment collection yet: when the trial ends, the owner is told and ops see it, and nothing locks
(D5).

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Ops (`OPS_ADMIN`) | Choose a clinic's plan at creation and later; see each clinic's plan and trial in the clinic list | Choose a plan smaller than what the clinic uses |
| Owner (`CLINIC_MANAGE`) | See the plan, its limits, what is used and the trial (*Plan*); see a notice when the trial has ended | Change the plan |
| Doctor, front desk | Nothing new (403 on the plan view) | — |

## 3. Domain model
- **Plan** (D4): `SOLO` 1 doctor and 2 users; `CLINIC` 3 and 5; `PLUS` (*Clinic Plus*) 5 and no
  user limit.
- **Subscription** (`clinic_subscriptions`, platform data, one row per clinic): the plan, whether a
  trial is owed (`has_trial`), the trial's start and end (both or neither, exactly 14 days), and the
  last plan change by ops.
- **Usage**: doctors are active doctor profiles; users are invited or active memberships (the owner
  counts; an invitation holds its seat until it is accepted or the member removed).

## 4. Behaviour
- **R1** Every clinic gets a subscription in the transaction that creates it: the plan ops chose
  (`CLINIC` when not said), or for an approved application `SOLO` for a solo doctor, else the
  smallest plan that fits its doctors.
- **R2** Migration 0041 gives every existing clinic `PLUS` with no trial. A clinic with no row
  (written straight to the database) is treated the same way.
- **R3** The trial starts when the clinic first becomes `ACTIVE` (its owner accepts the invitation)
  and lasts 14 days. It never restarts (reactivation after a suspension keeps it).
- **R4** Adding a doctor (`AddDoctor`, from ops, the owner or approval), inviting a new or
  deactivated member (`InviteStaff`, from ops, the owner or approval) and accepting an invitation
  (`AcceptInvite`, a re-check) are refused with 409 `SUB_LIMIT_REACHED` (`details.plan`, `limit`
  `doctors` or `users`, `allowed`) when the plan has no room. The check locks the clinic's
  subscription row, so two adds racing for the last place serialise. Re-inviting a still-invited
  member takes no new seat.
- **R5** Bringing an inactive doctor back (`PATCH /api/v1/clinic/doctors/{id}` with
  `is_active: true`) takes a place the same way.
- **R6** `GET /api/v1/clinic/subscription` (owners) answers the plan, its limits, the usage and the
  trial (`NOT_STARTED`, `ACTIVE` with whole days left rounded up, `ENDED`, or `NONE`).
- **R7** The ops clinic list shows each clinic's plan and trial state.
- **R8** `PUT /api/v1/ops/clinics/{id}/plan` (`OPS_ADMIN`) sets the plan; a plan smaller than what
  is used is 409 `SUB_PLAN_TOO_SMALL` (`details.limit`, `allowed`, `used`). Audited
  (`subscription.plan_changed`: from, to); the same plan again changes and records nothing.
- **R9** (D5) When the trial ends nothing is refused: owners see a notice on every page and ops a
  flag on the clinic list.
- **R10** No clinical or personal data is involved; the audit row holds the two plan codes.

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/clinic/subscription` | — | 200 `Subscription` | 401, 403 |
| PUT | `/api/v1/ops/clinics/{clinic_id}/plan` | `PlanInput` | 200 `Subscription` | 403, 404, 409 `SUB_PLAN_TOO_SMALL`, 422 |
| POST | `/api/v1/ops/clinics` | `NewClinic` gains `plan` | 201 | as before |
| GET | `/api/v1/ops/clinics` | — | items gain `subscription` (`PlanSummary`) | as before |
| POST/PATCH | doctors, staff invites, invitation accept | — | — | 409 `SUB_LIMIT_REACHED` |

Contract 0.49.0.

## 6. UI notes
*Settings → Plan* (`/settings/plan`, owners): the plan's name, "Doctors 1 of 3", "People in the team
(you included) 2 of 5" or "(no limit)", the trial's days left or that it ended, and "contact
MediEase" to change the plan. Owners see "Your free trial has ended. Everything keeps working;
contact MediEase to choose your plan." above every page once it has. The ops clinic list gains a
*Plan* column: the trial in words (an ended one in bold) and a plan picker with *Save plan*. A
refused add or invite shows the API's message ("The Solo plan allows 1 doctor. Ask MediEase to
change the plan.").

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| Ops change the plan | `subscription.plan_changed` | — | — |
| Trial starts | — (log `subscription.trial_started`; the clinic's `clinic.activated` row marks it) | — | — |
| A limit refuses an add | — (log `subscription.limit_reached`) | — | — |

## 8. Edge cases
- Two invitations racing for the last seat: the row lock lets one in; the other is 409.
- A plan lowered by hand below the usage (outside the API): new adds and accepting an invitation
  are refused until it fits.
- An application with more doctors than Clinic Plus allows (6 or more): approval is 409
  `SUB_LIMIT_REACHED` and nothing is created.

## 9. Acceptance criteria
- **AC1** A Solo clinic takes one doctor; the second is 409 with `limit: doctors`, `allowed: "1"`.
- **AC2** A Solo clinic takes two people (owner included); a third, from ops or the owner, is 409.
- **AC3** Ops change Solo to Clinic and a second doctor fits; the change is audited.
- **AC4** Ops cannot set Solo on a clinic with two doctors (409 `SUB_PLAN_TOO_SMALL`).
- **AC5** Bringing back a deactivated doctor when the plan is full is 409.
- **AC6** Accepting an invitation is re-checked against the plan.
- **AC7** The trial starts when the owner joins (14 days); once ended the owner's view and the ops
  list say so, and the owner still works.
- **AC8** A clinic from before plans is Plus with no trial; doctors and the desk cannot read the plan.

## 10. Observability
Logs `subscription.limit_reached` (clinic, plan, limit, used), `subscription.trial_started` and
`subscription.plan_set`.

## 11. Out of scope
Payment collection, invoices for the plan, card or UPI mandates, automatic downgrade or lock-out at
the end of the trial, patient or appointment limits, and self-service plan changes.

## 12. Open questions
None.
