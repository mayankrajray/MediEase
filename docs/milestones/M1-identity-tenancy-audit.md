# M1 — Identity, tenancy and audit: design notes

| Field | Value |
|---|---|
| Status | In progress — M1-P1 active |
| Spec | `docs/specs/identity-and-tenancy.md` (Approved 2026-10-02) |
| Covers | FR-ORG-01..04, FR-AUTH-01..04, FR-AUD-01..02, FR-OPS-01, FR-OPS-04, NFR-08, NFR-14 |
| Issue / branch / PR | #19 · `m1/19-identity-tenancy-audit` · one draft PR for the whole milestone (ADR-0011) |
| Exit criterion | An ops user onboards a clinic with an owner, doctor and front desk; each signs in and sees only their clinic; the tenancy suite proves isolation |

## Concepts to teach before code (CLAUDE.md "Teaching Expectations")

1. **Entities and value objects.** An entity has an identity that survives change (a clinic is the
   same clinic after it is renamed); a value object is defined by its value and validated once
   when created (`PhoneNumber("+919000000001")` is always E.164). Rules live on them, not in
   handlers.
2. **State machines.** Status fields change only through named methods that refuse illegal moves
   (`DEACTIVATED → ACTIVE` raises `CLN_INVALID_TRANSITION`).
3. **Repository pattern.** Application code asks a repository for domain objects; it never sees
   SQL or ORM rows. The SQLAlchemy adapter maps rows ↔ entities.
4. **Tenancy scoping by construction (ADR-0003).** A tenant repository is *built with* one
   `clinic_id`; none of its methods accept a clinic ID, so "forgot the `WHERE clinic_id`" cannot be
   written. Another clinic's row is simply not found (→ 404, R8).
5. **Unit of work.** One object owns the transaction: every repository used in a command shares one
   session, and the change commits or rolls back as a whole. P4 adds the audit writer to it, which
   is how R11 ("audit in the same transaction") holds.
6. **Time-ordered IDs (UUIDv7).** IDs are created by the application through `IdPort` (so entities
   have identity before they are saved) and sort by creation time (index-friendly).

## Phase plan

| Phase | Builds | Key decisions |
|---|---|---|
| P1 | Domain model, migration `0002`, tenancy-scoped repository base, unit of work, coverage gate | Below |
| P2 | Argon2id hashing, sign-in, refresh rotation with reuse detection, sign-out, lockout | Adds `password_hash`, lockout columns and `refresh_tokens` (migration `0003`); new settings for token secrets; designed at the start of P2 |
| P3 | Auth middleware → `RequestContext`; role + membership check on every route; permission matrix tests | R6, R7, R8, R10 |
| P4 | Append-only `audit_events` written through the unit of work; DB role with `INSERT, SELECT` only; `v_clinic_activity` | R11, AC5, AC6 |
| P5 | Ops API: create clinic → doctors → owner invite; onboarding checklist timestamps | R9, R12, FR-OPS-01/04 |
| P6 | Web: sign-in, clinic switcher, empty dashboard shell | Spec §6 |

Each phase starts with its design (`/plan-phase`), is approved, implemented, verified by the
developer and confirmed before the next phase starts. All phases are committed to the milestone
branch and appear in the one milestone PR.

---

## M1-P1 — Domain, tables, tenancy-scoped repositories

### What and why

The rest of M1 needs clinics, users, memberships and doctors to exist with their rules enforced,
and a persistence layer in which a cross-clinic query cannot be written. P1 builds exactly that,
with no HTTP endpoints and no auth (those are P2/P3).

### Domain (`domain/`, standard library only)

| Module | Contents |
|---|---|
| `shared/errors.py` | `DomainError` (stable `code`), `InvalidValue` (`REQ_VALIDATION_FAILED`, names the field), `InvalidTransition` (`CLN_INVALID_TRANSITION`) |
| `shared/phone.py` | `PhoneNumber` value object: strips spaces/`-`/`()`, accepts `+<E.164>`, Indian 10-digit, `0`-prefixed and `91`-prefixed input; `masked()` → `+91******3210` (the shared masking helper, CLAUDE.md "Logging") |
| `shared/email.py` | `EmailAddress` value object: trimmed, lower-cased, one `@`, dotted domain, ≤ 254 chars |
| `shared/time.py` | `require_utc(dt)` — timestamps entering the domain must be timezone-aware UTC |
| `clinics/clinic.py` | `Clinic` + `ClinicStatus` (`ONBOARDING → ACTIVE ↔ SUSPENDED`); `activate()` enforces **I1** (needs ≥ 1 active owner) with `CLN_OWNER_REQUIRED` |
| `clinics/doctor.py` | `Doctor`; **I3** non-empty qualification, registration number and council (FR-ORG-02); activate/deactivate |
| `identity/user.py` | `User` + `UserStatus` (`ACTIVE ↔ DISABLED`); email or phone required |
| `identity/membership.py` | `ClinicMembership`, `Role` (`OWNER`, `DOCTOR`, `FRONT_DESK`), `MembershipStatus` (`INVITED → ACTIVE → DEACTIVATED`); `change_role()` / `deactivate()` enforce **R9** (`CLN_LAST_OWNER`) given the clinic's active-owner count |

Entities receive `now` and IDs from their caller; the domain never reads the clock or generates IDs.

### Ports (`ports/`)

- `ids.py` — `IdPort.new_id() -> UUID`.
- `repositories.py` — `ClinicRepository`, `UserRepository` (platform: clinics and users are not
  tenant-owned); `DoctorRepository`, `MembershipRepository` (tenant: bound to one clinic).
- `unit_of_work.py` — `UnitOfWork` (context manager, `commit()`, `rollback()`, `clinics`, `users`,
  `tenant(clinic_id) -> TenantRepositories`).

### Adapters (`adapters/`)

- `ids/uuid7.py` — `Uuid7Generator` (RFC 9562 UUIDv7, monotonic within a process; Python 3.12 has
  no `uuid.uuid7`, so no dependency is added).
- `db/models/` — SQLAlchemy 2 typed models on one `Base` with a constraint naming convention.
- `db/tenancy.py` — `TenantScopedRepository`: holds the session and one `clinic_id`; every query
  starts from `_scoped_select()`; `_add()` refuses an entity from another clinic
  (`TenancyViolation`, a programming error, never a user-facing 404).
- `db/repositories.py` — the four repositories, mapping rows ↔ entities.
- `db/unit_of_work.py` — `SqlAlchemyUnitOfWork` (one session per unit; rolls back unless
  committed).
- `migrations/env.py` uses `Base.metadata`; migration `0002` creates the tables.

Nothing is wired into `bootstrap.py` yet: no route uses the unit of work until P2.

### Schema (migration `0002`)

`clinics`, `users`, `clinic_memberships`, `doctors` as in `docs/DATA_MODEL.md`, with these P1
decisions:

| Decision | Reason |
|---|---|
| `users.email` is `text` with `CHECK (email = lower(email))` + unique, not `citext` | No database extension (the app role may not be allowed to create one); the domain lower-cases emails |
| `users.password_hash`, `failed_login_count`, `locked_until`, `last_login_at` arrive in P2 (`0003`) | Only P2 has behaviour for them (CLAUDE.md "no placeholder code") |
| `clinics.patient_code_prefix`/`next_patient_seq` (M2), `booking_mode` (M3), `plan` (billing) are deferred | Added by the milestone that uses them |
| Status/role enums are `text` + `CHECK` | DATA_MODEL conventions |
| `doctors`: partial unique `(clinic_id, user_id) WHERE user_id IS NOT NULL` | One doctor profile per user per clinic (owner-who-is-a-doctor edge case) |
| Tenant indexes lead with `clinic_id` | ADR-0003 |

### Tests

- Unit (`tests/unit/domain/`): phone normalisation (valid forms, invalid forms, masking), email,
  each state machine (legal and illegal moves), I1, I3, R9, UTC enforcement; UUIDv7 version,
  variant and ordering.
- Integration (`tests/integration/db/`): migrations round-trip with `0002` as head; models and
  migration have no drift (Alembic autogenerate compare is empty); repositories round-trip each
  entity; unit of work commits, rolls back on exception and on exit without commit; DB constraints
  (I2 unique membership, email-or-phone, lower-case email, CHECK on enums).
- Tenancy (`tests/tenancy/`): two clinics — clinic A's repositories cannot `get` or `list` clinic
  B's doctors and memberships, cannot `update` them, and `add` refuses a B entity; every model with
  a `clinic_id` column has a `TenantScopedRepository` (guard against an unscoped table).

### Coverage gate (NFR-14)

`make test-api` and CI keep the whole-package gate (≥ 90%) and add
`coverage report --include` on `domain/` + `application/` with `--fail-under=80`.

### Verify

```bash
make up                      # migrate applies 0002; api healthy
make lint typecheck test     # all green; both coverage gates pass
make psql                    # \dt → clinics, users, clinic_memberships, doctors, alembic_version
```

Failure path: inserting a second membership for the same user and clinic fails with
`uq_clinic_memberships_clinic_id_user_id`; `tenant(clinic_a).doctors.get(<clinic B doctor id>)`
returns `None`.

### Risks

- Timezone validation uses the OS time-zone database through `zoneinfo`; both the API image and the
  dev venv have it (486 zones checked). If a slimmer base drops it, add the `tzdata` package.
