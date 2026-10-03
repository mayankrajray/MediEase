# Spec: Identity, tenancy and audit

| Field | Value |
|---|---|
| Requirements | FR-ORG-01..04, FR-AUTH-01..04, FR-AUD-01..02, FR-OPS-01, FR-OPS-04, NFR-08 |
| Milestone / phases | M1 / P1–P6 |
| Status | Approved (developer sign-off 2026-10-02) |
| Last updated | 2026-10-03 (§4 R13 and §8: accepting an invitation for an existing account now needs that account's current password and never changes it — a security amendment, approved by the developer 2026-10-03; earlier the same day: §7, §8 and §10 recorded the M1-P4 and M1-P5 audit actions, invitation flow and `auth.rejected` event) |

## 1. Context
Clinics must trust that only their own staff can see their patients, and that each staff member
sees only what their role needs (A13 needs separate doctor and front-desk access). Onboarding a
clinic must take under an hour (goal G4).

## 2. Actors and permissions
See the PRD §8.1 permission matrix — it is normative for this spec.

## 3. Domain model
- `Clinic` (status: `ONBOARDING → ACTIVE ↔ SUSPENDED`)
- `User` (status: `ACTIVE`, `DISABLED`; lockout fields)
- `ClinicMembership` (role: `OWNER | DOCTOR | FRONT_DESK`; status: `INVITED → ACTIVE → DEACTIVATED`)
- `Doctor` (optional link to a `User`)
- `AuditEvent` (append-only)

Invariants:
- **I1** A clinic in `ACTIVE` status has at least one `ACTIVE` owner membership.
- **I2** A user has at most one membership per clinic.
- **I3** A doctor who issues prescriptions has non-empty qualification and registration number.

## 4. Behaviour
- **R1** Sign-in accepts an email or phone identifier; phone is normalised to E.164 first.
- **R2** Wrong credentials return `AUTH_INVALID_CREDENTIALS` without revealing which part was wrong
  and take a constant-time path whether or not the user exists.
- **R3** After 5 consecutive failures, the account is locked for 15 minutes (`AUTH_LOCKED`);
  a successful sign-in resets the counter.
- **R4** Successful sign-in sets `me_access` (15 min) and `me_refresh` (14 days) cookies and a
  CSRF cookie; response body contains the user and memberships, never tokens.
- **R5** Refresh rotates the refresh token; presenting an already-rotated token revokes the whole
  family and returns `AUTH_REFRESH_REUSED`.
- **R6** Every authenticated request resolves exactly one active clinic: the only membership, or
  the one named in `X-Clinic-ID`; otherwise `PERM_CLINIC_REQUIRED`.
- **R7** Deactivated memberships and disabled users are rejected on the next request
  (`AUTH_ACCOUNT_DISABLED`) — no cached permissions beyond the request.
- **R8** Tenant resources outside the active clinic return `REQ_NOT_FOUND`.
- **R9** Owners cannot remove or demote the last active owner (`CLN_LAST_OWNER`).
- **R10** Ops users (`is_platform_ops`) can call `/api/v1/ops/*` only; they have no clinic
  membership by default and no access to clinical endpoints.
- **R11** Audit events are written in the same transaction as the change; if the audit insert
  fails, the change fails.
- **R12** The onboarding checklist records the first time each milestone step happens; later
  repeats do not overwrite timestamps.
- **R13** Holding an invitation link does not prove owning the account it is for (the inviting
  owner receives it). Accepting for a **new** account sets its password; accepting for an account
  that **already has a password** requires that account's current password, never changes it, and
  counts wrong attempts towards the R3 lockout (`AUTH_INVALID_CREDENTIALS`, `AUTH_LOCKED`).

## 5. API surface
See API.md "Auth and session", "Clinic administration", "Ops console".

## 6. UI notes
- Sign-in page: single identifier field + password; error text from the error message.
- Clinic switcher appears only for users with more than one membership.
- Ops "Create clinic" is a 3-step wizard: clinic → doctors → owner invite; shows elapsed time.

## 7. Events and side effects
| Trigger | Audit action | Analytics |
|---|---|---|
| Sign-in success / failure | `auth.signed_in` / `auth.sign_in_failed` | — |
| Sign-out, refresh token replayed | `auth.signed_out` / `auth.refresh_reused` (M1-P4) | — |
| Staff invited / accepted / role changed / deactivated | `staff.invited` / `staff.accepted` / `staff.role_changed` / `staff.deactivated` | — |
| Clinic created / activated / edited | `clinic.created` / `clinic.activated` / `clinic.updated` | `clinic_onboarding_step_completed` |
| Doctor added / edited | `doctor.added` / `doctor.updated` (M1-P5) | — |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| Same phone used by a doctor in two clinics | One user, two memberships; switcher shown |
| Owner is also a doctor | Owner membership + linked Doctor profile; doctor permissions apply to clinical actions |
| An invited member never accepts | The invitation expires after 7 days; the clinic invites them again, which retires the old link (M1-P5) |
| An invitation link is used twice | The second attempt is refused as already used; they sign in instead (M1-P5) |
| An invitation is for an email or phone that already has an account | The page asks for that account's current password instead of a new one (R13); a wrong one is refused and counted, and the invitation stays pending |
| A person with a password but no active membership is invited again | They can still accept, by entering their password: sign-in refuses them (`AUTH_ACCOUNT_DISABLED`), so acceptance is how they come back |
| Password reset requested (P1) | Not available in M1; ops resets manually with audit |
| Clock skew between api replicas | Token validation allows 30 s leeway |

## 9. Acceptance criteria
- **AC1 (FR-AUTH-04)** Given 5 failed sign-ins, when a 6th attempt uses the correct password within
  15 minutes, then the response is 423 `AUTH_LOCKED`.
- **AC2 (FR-AUTH-02)** Given a refresh token that was already rotated, when it is presented, then
  the response is 401 `AUTH_REFRESH_REUSED` and the newer token in the family also stops working.
- **AC3 (FR-AUTH-03, NFR-08)** Given users in clinics A and B, when user A requests any B resource
  by ID, then the response is 404 and no B data appears in any A list endpoint.
- **AC4 (FR-ORG-04)** Given a front-desk user is deactivated, when their next request arrives with a
  valid access token, then it is rejected with `AUTH_ACCOUNT_DISABLED`.
- **AC5 (FR-AUD-01)** Given staff role change, then exactly one `staff.role_changed` audit event
  exists with actor, target and `request_id`.
- **AC6 (FR-AUD-02)** Given the application database role, when an `UPDATE audit_events` is
  attempted, then the database refuses it.

## 10. Observability
Events: `auth.sign_in_failed` (with `reason` enum), `auth.locked`, `auth.refresh_reused`,
`auth.rejected` (per-request authentication, with `reason`: `invalid_token`, `session_ended`,
`account_disabled`, `unknown_user` — added in M1-P3), `perm.denied`, `tenancy.not_found`.
Metric: sign-in failures per minute.

## 11. Out of scope
OTP sign-in, password reset by message, support-access grants, SSO.

## 12. Open questions
None blocking. Resolved at approval (2026-10-02):
- Do clinics want the front desk to see prescription *existence* on the queue? **Yes, a flag
  only** (PRD §8.1 permission matrix); revisit with pilot feedback in M4.
