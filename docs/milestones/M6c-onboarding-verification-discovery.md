# M6c — SaaS clinic onboarding, verification and discovery: design notes

| Field | Value |
|---|---|
| Status | Proposed 26 Oct 2026; **approved by the developer 26 Oct 2026** (the phase plan, milestone decisions M1–M6 and the P1 design) with decisions D1–D4 locked below. Opened after M6b merged (PR #52). P1 built 26 Oct 2026 (as-built notes below), awaiting confirmation and push |
| PRD | v1.2 §0 (C7, C8, C14), §8.9, §8.14 (FR-ONB, FR-DIS, FR-LND), NFR-17, NFR-19 |
| Specs | `docs/specs/clinic-onboarding.md` (P1 Approved; P2–P4 written at their start); `docs/specs/discovery.md` (written at P5) |
| ADR | ADR-0020 (Accepted): clinic applications are platform data, kept apart from clinics, and the applicant has no account until approval |
| Covers | FR-ONB-01..10, FR-DIS-01..08, FR-LND-01..03, NFR-17, NFR-19 |
| Issue / branch / PR | #53 · `m6c/53-onboarding-discovery` (from `main` at `9df830b`, after PR #52 merged) · one PR for the milestone (ADR-0011) |
| Exit criterion | A pending, approved-but-unlisted or suspended clinic is invisible in discovery; an `ACTIVE`, verified and listed clinic is found by clinic search and by doctor search and requested within one session; `make e2e` green |
| Out of scope | Payments, plans and trials (M6d, FR-SUB-01); automatic council-register lookups (no public API; checks stay manual); maps, coordinates and radius search; ratings, reviews, ads or paid ranking (FR-DIS-04 forbids them); WhatsApp to applicants; deployment (M9) |

## Facts the design rests on (checked in the code, 26 Oct 2026)

- **Clinic status** is `ONBOARDING → ACTIVE ↔ SUSPENDED` (`domain/clinics/clinic.py`). A clinic
  becomes `ACTIVE` only when an owner accepts the invitation (`AcceptInvite`); nothing else
  activates it. **No suspend or reactivate use case or route exists** (`Clinic.suspend()` has no
  caller). A suspended clinic's staff routes are refused (`CLN_SUSPENDED`), its jobs are cancelled,
  its public page is 404 and its patient notices are hidden; its open booking requests are
  **not** cancelled.
- **`Clinic.has_public_page`** is `status is ACTIVE`, with the comment "M6c adds 'and verified'
  here only". There is no verification, listing, language, fee, description or coordinate field
  on clinics or doctors.
- **Ops** is one boolean, `users.is_platform_ops`, behind the `@ops` policy; ops users are refused
  on clinic routes. There is no reviewer role.
- **The ops wizard** is a sequence of calls: `CreateClinic` (clinic in `ONBOARDING` plus the
  checklist), `AddDoctor` (each needs qualification, registration number and council), staff
  invites (`InviteStaff`, which can link the owner to a doctor profile: "Doctor 1"), schedules and
  a CSV import. The invite link is shown once (`accept_url`), or emailed when an owner invites.
- **Doctors** carry display name, qualification, registration number and council, an optional
  specialty, `is_active` and an optional user link.
- **Public surface (M6b-P4):** `/api/v1/public/clinics/{slug}` and its availability, allow-listed
  bodies, `no-store`, `noindex`; the web page `/c/{slug}` is `noindex` "until a clinic is
  verified (M6c)". Fixed-window rate limits in `public_rate_limits`, IPs as HMAC digests.
- **Storage:** `BlobStoragePort` is private and write-once (`put`, `get`, `exists`; no delete),
  served only through the authenticated API. There is **no upload endpoint** and no file-type
  check anywhere; the only raw upload is the ops CSV import (2 MiB).
- **Email:** `EmailPort` over SMTP from jobs; templates are Python functions. `email_tokens`
  must belong to a staff user or a patient account, so it cannot verify an applicant.
- **Audit:** actor types `STAFF`, `OPS`, `PATIENT_LINK`, `SYSTEM`, `PATIENT`; events may have no
  clinic (sign-in). Metadata holds IDs and enums only.
- **Search:** prefix `LIKE` on lower-cased names only; no `pg_trgm`, full-text or PostGIS. Clinics
  have `city`, `state` and `pincode` text only.
- **The root page** `/` redirects to *Today*; signed-out visitors land on sign-in. There are no
  marketing pages.

## Phase plan

| Phase | Builds | Requirements | Design |
|---|---|---|---|
| P1 | **The application.** A public `/apply` form for a clinic or a solo doctor: clinic, owner, doctors with registration details and a certificate each; the applicant's email verified by a link; the application record and its lifecycle states; rate limits and the duplicate flag; the confirmation email | FR-ONB-01, 02, 07 | Below |
| P2 | **The reviewer's workflow.** Ops roles (`OPS_ADMIN`, `OPS_REVIEWER`); the queue; take an application (`UNDER_REVIEW`); the certificate viewer; a check per doctor (register looked up, certificate matches, result, note); approve or reject with a reason; the applicant told by email, with a status page; re-applying | FR-ONB-03, 05 (rejection), 07 (duplicates shown) | At its start |
| P3 | **Approval into the one creation path, and verification.** Approval opens the ops Create-clinic wizard pre-filled from the application; the wizard creates the clinic (`ONBOARDING`), its doctors and the owner's emailed invitation (owner as Doctor 1 where they practise), recording the clinic and the checked doctors as verified against the application. Ops-created clinics start unverified and are verified by the same per-doctor checks. `has_public_page` becomes `ACTIVE ∧ verified` | FR-ONB-04, 06, 08, FR-PUB-01 | At its start |
| P4 | **Suspension and listing.** Suspend and reactivate (ops, with a reason); on suspension the clinic leaves every public surface at once and its open booking requests are withdrawn with the patients told. The owner's *Listed in MediEase directory* switch and each doctor's *Visible* switch, allowed only when the listing requirements hold, with the reasons shown. The one discoverability rule | FR-ONB-05, 09, 10 | At its start |
| P5 | **Public profiles.** The clinic profile (the `/c/{slug}` page grown: specialties, languages, optional fee) and a doctor profile; new published fields; indexable when discoverable unless the clinic opts out, `noindex` otherwise; a sitemap of discoverable profiles | FR-DIS-03, 06, 07 | At its start |
| P6 | **Search.** Clinic search and doctor search with the city/PIN, speciality, language and "available in the next 7 days" filters, ordered by relevance, then place, then availability; a directory read model; < 500 ms at pilot scale | FR-DIS-01, 02, 04, 05 | At its start |
| P7 | **Discovery to booking.** *Find a doctor* in the portal and on the public site: search → profile → a time → sign in or up and return to it → the M6b request; a profile that stops being discoverable answers exactly like not found | FR-DIS-08, NFR-19 | At its start |
| P8 | **Landing page v1.** `/` for signed-out visitors: the clinic path (benefits, features, pricing, *Apply to join MediEase*, book a demo) and the patient path (*Find a doctor*, sign in with Google), English and Hindi, LCP < 2.5 s on 4G, indexable, analytics events without PII | FR-LND-01..03 | At its start |

Testing follows the 26 Oct 2026 rule: per phase, the tests for the changed code plus lint and
typecheck; the full API and Playwright suites once, at the end of P8.

## The developer's decisions (26 Oct 2026)

Locked when M6c was approved; they override anything below that reads otherwise.

| # | Decision |
|---|---|
| D1 | A clinic becomes `ACTIVE` when the owner accepts the existing invitation (milestone decision M5 as recommended). The other checklist items are measures, not gates |
| D2 | `/apply` is **English-only in M6c** (P1 point 8). Hindi on the clinic side is not planned in this milestone; the landing page (P8) decides its own languages under FR-LND-02 |
| D3 | The application says **MediEase will reply within 2 working days** (P1 point 8, spec R23) |
| D4 | The M6c issue (#53) opened at once; the branch cut from the latest `main` after PR #52 merged; the design documents committed there |

## Milestone decisions (approved)

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| M1 | Where an application lives | **Platform data**, not tenant data: no clinic exists until approval (FR-ONB-02), so the application cannot carry a `clinic_id`. Reached only through reviewed platform repositories used by the applicant's public routes and the ops routes. Personal data (C2) under the same rules as staff contact details. ADR-0020 | B: create the clinic at submission in a new `APPLIED` status (FR-ONB-02 and the PRD's status table forbid it: `Clinic.status` must never say whether a clinic applied) |
| M2 | The applicant's identity | **No account until approval.** The application holds the owner's name, phone and email; the email is verified by a single-use link sent to it. Approval creates the staff user through the existing invitation (P3) | B: require a staff account first (FR-ONB-02: no user before approval). C: require a patient account (a patient identity is not a clinic owner) |
| M3 | Ops roles | `users.ops_roles` (`OPS_ADMIN`, `OPS_REVIEWER`) replaces the boolean in P2; every existing ops user gets both, so nothing changes for them. Reviewing needs `OPS_REVIEWER`; creating clinics, imports and messaging costs need `OPS_ADMIN`; suspension needs `OPS_ADMIN` | B: keep one ops boolean (the PRD names `OPS_REVIEWER`; separating who verifies doctors from who sets clinics up is the point) |
| M4 | Verification | Recorded **per clinic and per doctor**: who, when, and against what (`APPLICATION` or `OPS_CHECK`), never inferred from status. A doctor's verification is its own check row (council, number, register looked up, certificate seen, result). Editing a verified doctor's registration number or council clears that doctor's verification (to be re-checked) | B: one `verified` flag on the clinic (FR-ONB-09 needs doctors verified one by one) |
| M5 | Activation (**D1**) | **Keep today's rule** for `ACTIVE`: the owner accepting the invitation. FR-ONB-04's "checklist complete" is read as the steps that are required before a patient can be served: clinic created, a doctor added, the owner joined. The remaining checklist items (first appointment, first prescription) stay as measures (G4), not gates | B: activate only when every checklist item has a time (a clinic could never book its first appointment, since booking needs `ACTIVE`) |
| M6 | Search technology | PostgreSQL only: `pg_trgm` for names and a **directory read model** (a platform table of discoverable clinics and doctors, refreshed in the same transaction as every change that affects it and rebuilt by a job), designed in P6 and recorded then as an ADR. "Distance" means same PIN, then same city, then same state, because no coordinates are stored | B: an external search service (cost and one more data processor for pilot scale). C: geocoding addresses now (a provider, consent wording and accuracy questions for little gain at pilot scale) |

---

## M6c-P1 — The application

Proposed 26 Oct 2026; **approved 26 Oct 2026** with D2 and D3. Covers FR-ONB-01, FR-ONB-02 (the
record and its states) and FR-ONB-07. Rules: `docs/specs/clinic-onboarding.md` R1–R23 (Approved). The reviewer's side (taking, checking,
deciding) is P2; until then applications wait in `PENDING` and ops can list them read-only.

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| 1 | What is stored | Platform tables (migration `0032`): **`clinic_applications`** (reference `MA-2026-0001`, kind `CLINIC` or `SOLO_DOCTOR`, status, clinic name, address line, city, state, PIN, clinic phone, specialties, owner name, owner phone, owner email, `owner_practises`, `email_verified_at`, the verification secret's digest and expiry, `submitted_at`, `ip_hash`, `duplicate_of` flags, `created_at`, `updated_at`); **`clinic_application_doctors`** (application, position 1–10, name, qualification, council, registration number, `is_owner`, certificate key, content type, size, SHA-256). The reviewer's columns (who took it, decision, reason) arrive in P2 | B: one JSON document per application (no constraints, no duplicate index on registration numbers) |
| 2 | Who applies, and the form | Anyone, signed out, at **`/apply`**. *A clinic* (1–10 doctors) or *I am a doctor with my own practice* (exactly one doctor, the owner). Clinic: name, address, city, state, PIN, phone, specialties (from a list, up to 10). Owner: name, mobile, email, "I also see patients here" (then the owner is one of the doctors). Each doctor: name, qualification, council (a fixed list: the National Medical Commission and the state medical councils), registration number, certificate. Nothing about patients, fees or hours | B: collect hours and booking mode too (that is onboarding, P3, and changes before go-live) |
| 3 | The certificate | One file per doctor, **PDF, JPEG or PNG, at most 5 MB**, checked by its first bytes, not its name or declared type; stored privately with the blob port under `applications/{id}/doctor-{n}` and never public; its SHA-256 recorded. Read only by reviewers through the audited ops route in P2. The storage port gains `delete` for application files only (retention, point 9) | B: accept any image or Word file (a wider parser surface for no need). C: a link to the certificate (unverifiable, may disappear) |
| 4 | Submitting | One **`multipart/form-data`** request, `POST /api/v1/public/applications`: a JSON part `application` and one file part per doctor; all or nothing; at most 30 MB in total. Validation errors name the field (`doctors.1.registration_number`). Answer 202 with the reference and the masked email: "Check your email to confirm your application" | B: create a draft, then upload files one by one (half-made rows and a resumable flow to protect). C: base64 files inside JSON (a third larger, harder size limits) |
| 5 | The verified email (FR-ONB-01, FR-AUTH-08) | On submission the application is **`PENDING` with the email unverified**; a link `PUBLIC_BASE_URL/apply/confirm/{token}` (a 256-bit secret, SHA-256 digest stored, 48 hours) is emailed. Opening it sets `email_verified_at`; only then does the reviewer queue show it, and the confirmation email "We received your application MA-2026-0042" is sent. A second submission with the same email while one is unverified replaces it (the old one and its files are deleted). Unverified applications are deleted after 72 hours | B: a 6-digit code typed on the form before submitting (one more round trip on the form; codes are easier to guess and need their own lockout). C: no verification (FR-ONB-01 asks for it, and the owner's invitation goes to that address) |
| 6 | The lifecycle in P1 | The status column and its CHECK hold all four states, `PENDING`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, from the start; P1 writes only `PENDING`. The domain entity owns the transitions (P2 uses them). An application never changes a clinic, user or membership | B: add states as phases need them (a migration per phase on one CHECK) |
| 7 | Abuse controls (FR-ONB-07, NFR-19) | Per address 5 submissions a day; per owner phone 3 a day and per owner email 3 a day (counted from the table, never put in a bucket name, as M6b-P4 did for phones); a hidden field that a person never fills; 429 `ONB_RATE_LIMITED` with `Retry-After`. **Duplicates are flagged, not refused:** a registration number with its council already in another open or approved application, or on an existing doctor, marks the application `possible_duplicate` with the matches' references for the reviewer. The applicant is not told (it would reveal another clinic's application) | B: refuse duplicates (a doctor who works at two clinics applies twice, legitimately). C: CAPTCHA (a third-party script; revisit if abuse appears) |
| 8 | What the applicant sees (**D2, D3**) | `/apply` (360 px first, under 200 KB, **English only in M6c**), with a plain note that MediEase checks each doctor's registration by hand and **will reply by email within 2 working days**. After submitting: "Check your email". The confirm page: "Thank you. We received application MA-2026-0042 and will email you." The status page and the decision emails are P2 | B: Hindi now (the form's council and qualification terms are English on the certificates themselves; the landing page decides the site's languages) |
| 9 | Retention and privacy | Applications are C2 personal data plus the certificates. Unverified: deleted after 72 hours. Rejected: kept 180 days for re-application and duplicate checks, then deleted with their files. Approved: kept while the clinic exists (the verification evidence). Logs carry the application ID, the reference and counts; never a name, phone, email, registration number or file name. Audit (no clinic): `application.submitted` and `application.email_verified`, actor **`APPLICANT`** (a new actor type with no user), metadata IDs, kind and doctor count only | B: keep everything forever (no reason to hold rejected applicants' certificates) |
| 10 | Ops in P1 | Read-only: `GET /api/v1/ops/applications` lists verified applications (reference, kind, clinic name, city, doctors, submitted, the duplicate flag) for `@ops`; no detail, certificate or decision until P2. No new web screen in P1 beyond a count on the ops clinic list ("3 applications waiting") | B: nothing for ops until P2 (applications would arrive unseen) |

Fixed points:

- **Migration `0032`:** the two tables above; unique reference; an index on
  `(registration_council, registration_number)` for the duplicate check; the job kinds
  `send_application_email` (system) and `purge_applications` (daily, folded into the existing
  purge if simpler); the audit actor type `APPLICANT`.
- **Contract 0.36.0:** `POST /public/applications` (multipart), `POST
  /public/applications/confirm` (`{token}`), `GET /ops/applications`; schemas
  `ClinicApplicationInput`, `ApplicationReceipt`, `OpsApplicationSummary`.
- **Errors:** `ONB_RATE_LIMITED` (429), `ONB_FILE_REJECTED` (422: type, size or unreadable, with
  the doctor's position), `ONB_CONFIRM_INVALID` (404: unknown, used or expired link, one
  answer). Field errors are `REQ_VALIDATION_FAILED`.
- **Code:** `domain/onboarding/application.py` (entity, states, rules), `ports/onboarding.py`,
  `adapters/db/applications.py`, `application/onboarding/` (submit, confirm, list, purge),
  `delivery/http/public_applications.py`; a file-type sniffer in the domain (first bytes only, no
  parsing library).
- **Unchanged:** clinics, the wizard, every existing route.

Planned verification:

- **Unit:** the application rules (kinds and doctor counts, owner-as-doctor, specialties, PIN,
  phone, council list); the transitions; the file sniffer (a PDF renamed `.png`, an EXE renamed
  `.pdf`, an empty file, 5 MB + 1 byte).
- **Integration (PostgreSQL):** a submission stores the rows and the files and enqueues one
  email; confirming once works, twice is `ONB_CONFIRM_INVALID`; an unconfirmed one is not listed
  for ops; a resubmission with the same email replaces it; the limits; a duplicate registration
  number flags both references; the purge deletes rows and files; logs and audit rows carry no
  name, phone, email or registration number.
- **Contract and structure:** the multipart route against the contract; migrations; the worker's
  new kinds; platform repositories outside `uow.tenant`.
- **Web:** the form's steps, validation and the file picker; the confirm page.
- **Playwright (360 px):** apply as a solo doctor with a PDF, confirm from Mailpit, see the
  thank-you page; ops sees it listed. Failure path: a `.txt` renamed `.pdf` is refused on that
  doctor's row.

Open questions: none. The three asked at the proposal were answered by D1, D2 and D3.

### As built (M6c-P1)

Built 26 Oct 2026 to the approved design with D1–D4. Details settled in the build, and where it
differs from the design:

- **Storage.** Migration `0032`: `clinic_applications` and `clinic_application_doctors` (platform
  tables, no `clinic_id`), the sequence `clinic_application_reference_seq` for `MA-<year>-NNNN`
  (never reused, across years), CHECKs tying the confirmation digest to an unconfirmed
  application and review states to a confirmed one, a unique digest, and the doctors'
  `(council, number)` index for duplicates. The doctors' table is cascaded from its application.
  `audit_events.actor_type` gains `APPLICANT`; `ck_jobs_system_kind` gains
  `send_application_email` and `purge_applications`. Downgrade is refused while applicant audit
  rows exist (the audit table is append-only), as for `PATIENT`.
- **The form** is one `multipart/form-data` request (JSON part `application`, files
  `certificate_<n>`), at most 30 MB; field errors name doctors from 1. Registration numbers are
  stored normalised (spaces removed, upper case). Councils and specialties are published lists in
  `domain/onboarding/lists.py`; the web copy in `features/apply/lists.ts` is checked against it by
  an API test, as is the reply promise (D3). The honeypot field `website` answers 202 with a
  made-up reference and keeps nothing.
- **Certificates** are written to blob storage before the transaction under
  `applications/{id}/doctor-{n}`; a failed write deletes what was written and answers 503
  `ONB_UPLOAD_FAILED`; a failed transaction deletes the files. `BlobStoragePort` gains `delete`
  (local and S3), used only for application files.
- **The email link** is minted by the `send_application_email` job when it sends, as the account
  emails are (ADR-0016): no usable secret at rest, and a retry replaces the link. It expires 48
  hours after the application, not after the email. The confirm page needs a button press, so a
  mail scanner that fetches the link confirms nothing.
- **Limits** are counted from the applications table per address, owner phone and owner email
  (24 hours), because the M4-P5 limiter keeps windows for an hour only; confirming uses the
  limiter (20 a minute per address). Over a limit: 429 `ONB_RATE_LIMITED` with `Retry-After`.
- **Duplicates** match other confirmed, not rejected applications by council and number, and
  existing doctors by the normalised **number alone** (ops-created doctors have a council typed
  by hand). The flag is stored as references and `clinic:<id>`; the applicant's answer is
  identical either way.
- **Purge** is hourly (`purge_applications`), not part of the daily retention job, so an
  unconfirmed application goes at most an hour after its 72 hours. It logs a count only.
- **Ops.** `GET /ops/applications` (summary only) and *N applications waiting* under the clinics
  on `/ops`, read-only until P2.
- **Web.** `/apply` (five steps; client-side checks for every rule the form can check; the API's
  field errors bring the person back to the step concerned; English only, D2; the reply promise on
  the first step, the review and the page after sending, D3) and `/apply/confirm/{token}`. Both
  are public paths in the proxy. The shared client gains `apiPostForm` for multipart requests.
- **Measured** at 360 px: `/apply` 158 KB on a first load; axe found nothing serious on the form,
  the doctors' step or the confirm page.

Differences from the design:

- An error code was added: `ONB_UPLOAD_FAILED` (503) for R10.
- The purge is hourly rather than folded into the daily purge.
- Existing doctors are matched by number alone (above).
- Dental, AYUSH and other councils are not on the list: the list is the National Medical
  Commission and the state medical councils, as FR-ONB-03 names. A clinic of another kind cannot
  apply yet; to decide when the first one asks.

Tests (changed code only, per the 26 Oct rule): domain (`test_clinic_application.py`, 34: the
form's rules, the sniffer, the lifecycle), the lists-match test, integration
(`test_clinic_applications_http.py`, 15: AC1–AC9 and the failure paths), the contract test,
migrations (`test_0032_*`), route policies, storage `delete` on both adapters; web (the form,
the confirm page, the ops list, the proxy); Playwright `clinic-application.spec.ts` (apply at 360
px, the renamed text file refused, confirm from Mailpit, the used link, ops sees it). Also run:
unit, tenancy, contract, migration and job suites (1,532), the full web suite (655), and the
Playwright `workspaces`, `portal-accounts` and `password-reset` journeys.

---

## M6c-P2 - The reviewer's workflow

Designed 26 Oct 2026 and **approved in advance by the developer** (26 Oct 2026: every design
decision for P2-P8 approved; the milestone PR waits for the developer's final approval). Covers
FR-ONB-03, FR-ONB-05 (rejection) and the reviewer's side of FR-ONB-07. Rules:
`docs/specs/clinic-onboarding.md` R24-R40.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | Ops roles (milestone M3) | `users.ops_roles` (`OPS_ADMIN`, `OPS_REVIEWER`; migration `0033`), every existing ops user backfilled with both, so nothing changes for them. `@ops` routes (clinics, imports, costs) need `OPS_ADMIN`; the review routes need `OPS_REVIEWER`. `is_platform_ops` stays as "is MediEase staff" (the session and clinic-route refusal rules are unchanged) | One boolean (the PRD names the reviewer role) |
| 2 | What a reviewer sees | The full application: clinic, owner contact, each doctor's registration and certificate, the duplicate matches. Opening the detail is audited (`application.viewed`), each certificate download too (`application.certificate_viewed`). No clinical content exists in an application | A summary only (the reviewer must see the registration and certificate to check them) |
| 3 | Taking an application | `POST /ops/applications/{id}/take`: `PENDING` (confirmed) -> `UNDER_REVIEW` with the reviewer and time, under the row lock; a second reviewer taking it is 409 `ONB_ALREADY_TAKEN`. Any reviewer may continue an application already under review (shifts change); the record keeps who took it | Exclusive locks per reviewer (a reviewer off sick would block the queue) |
| 4 | Checking a doctor | `PUT .../doctors/{doctor_id}/check`: register looked up (yes/no), certificate matches (yes/no), result `VERIFIED` or `NOT_VERIFIED`, a note up to 500 characters (the reviewer's own words, never sent). Allowed only `UNDER_REVIEW`; a new check replaces the earlier one; each is audited (`application.doctor_checked`). `VERIFIED` needs both yes | Checks outside the review (nothing to attach them to) |
| 5 | Rejecting | `POST .../reject` with a reason code (`REGISTRATION_NOT_FOUND`, `CERTIFICATE_UNCLEAR`, `DETAILS_DO_NOT_MATCH`, `NOT_ELIGIBLE`, `DUPLICATE`, `OTHER`) and a message to the applicant (1-500 characters, required for `OTHER`). `UNDER_REVIEW` -> `REJECTED` with reviewer, time, reason; audited; the applicant is emailed the reason's words and the message. They may apply again (a new application) | Free text only (no consistent reporting) |
| 6 | Approving | Arrives with P3, because approving creates the clinic (FR-ONB-08: one creation path). P2 shows *Approve* only when every doctor is `VERIFIED`, and it opens P3's prefilled form | Approve now and create later (an `APPROVED` application with no clinic) |
| 7 | Retention (R21) | Rejected applications are deleted with their certificates 180 days after the decision by the hourly purge; approved ones are kept while the clinic exists | Keep rejected forever |
| 8 | The applicant's status | Told by email at each decision (received, rejected; approved in P3 with the invitation). No status page: the applicant has no account, and a second token would need its own lifecycle for little gain | A token status page (another secret in another inbox) |
| 9 | The ops screens | `/ops/applications`: the queue by status (waiting, under review, decided), oldest first, with the duplicate flag. `/ops/applications/{id}`: the details, each doctor with *Open certificate* (fetched through the API, shown in a new tab as a blob, never a public link) and the check form, *Take*, *Reject*. 1280 px first (ops work at a desk) but usable at 768 px | A drawer on the list (too much to check in a drawer) |

Storage: migration `0033`: `users.ops_roles`; `clinic_applications` gains `taken_by`, `taken_at`,
`decided_by`, `decided_at`, `decision_reason`, `decision_message`; `clinic_application_checks`
(one row per application doctor: who, when, the two answers, the result, the note). Contract
0.37.0. Errors: `ONB_ALREADY_TAKEN` (409), `ONB_NOT_UNDER_REVIEW` (409), and the existing
`PERM_DENIED` for an ops user without the role.

---

## M6c-P3 - Approval into the one creation path, and verification

Designed 26 Oct 2026; **approved in advance** (as P2). Covers FR-ONB-04, 06, 08 and FR-PUB-01's
"verified". Rules: spec R41-R49.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | One creation path (FR-ONB-08) | `CreateClinic`, `AddDoctor` and `InviteStaff` each gain an `in_transaction(uow, ...)` that holds their whole rule set; their `execute` wraps it. `ApproveApplication` calls the three in **one transaction**: the clinic (`ONBOARDING`), each doctor, the owner's invitation (emailed; the owner linked to their doctor profile as Doctor 1 when they practise), the verification records and `APPROVED`. Any failure (for example a slug taken) leaves nothing | Run the three use cases one after another (a failure half-way leaves a clinic with no owner) |
| 2 | The prefilled wizard | *Approve and create the clinic* opens a form prefilled from the application: name, address, phone, specialties, the doctors, the owner; the reviewer chooses the **slug** (suggested from the name), the booking mode and the time zone (default Asia/Kolkata), and may correct the clinic's details. The doctors and owner come from the application unchanged | Reuse the four-step ops wizard (built for ops typing everything; every value is already known here) |
| 3 | Verification records (milestone M4) | `clinics.verified_at`, `verified_by`, `verification_source` (`APPLICATION` \| `OPS_CHECK`), `application_id`; `doctors.verified_at`, `verified_by`, `verification_source`. Approval verifies the clinic and every doctor (source `APPLICATION`). Migration `0034` | A flag on the clinic only |
| 4 | Ops-created clinics (FR-ONB-06) | Start **unverified**. A reviewer verifies each doctor (`POST /ops/clinics/{id}/doctors/{doctor_id}/verify`, the same two answers as an application check) and then the clinic (`POST /ops/clinics/{id}/verify`, allowed once at least one active doctor is verified); source `OPS_CHECK`, audited | Mark them verified when created (FR-ONB-06 forbids it) |
| 5 | When verification ends | Changing a verified doctor's registration number or council clears that doctor's verification (to be checked again). Nothing else clears it | Clear on any change (names, qualifications are corrected often and checked against the same certificate) |
| 6 | `has_public_page` (FR-PUB-01, FR-ONB-02) | `ACTIVE ∧ verified`, in the one domain property. The public page, its availability and new booking requests all use it (one 404). Existing demo clinics are verified by `make seed`; no production clinic exists yet | Keep `ACTIVE` only until P4 (unverified clinics would take requests) |
| 7 | The owner's email | The invitation goes by email (the existing `send_staff_invite` job) to the application's verified address; the reviewer also sees the accept link once, as for ops invites, to send by hand if needed | Link only (the applicant asked by email and expects it there) |
| 8 | Activation (D1) | Unchanged: the clinic becomes `ACTIVE` when the owner accepts | — |

### As built (M6c-P2, P3)

Built 26-26 Oct 2026 to the designs above. Details settled in the build:

- **Roles.** `OpsRole` and `User.ops_roles` in the domain; `User.create` gives a new ops user both
  roles. `AccessPolicy` gains `ops_role`; `@ops` now means `OPS_ADMIN`, the new `@reviewer`
  `OPS_REVIEWER`. `/me` returns `ops_roles`, and the ops navigation and home show each screen only
  to its role (`OpsHome`, `OpsShell`).
- **The application's clinic** is stored as `created_clinic_id`, not `clinic_id`, so the
  platform table never looks like a tenant table to the scoping guard.
- **The queue** without `queue=` lists every confirmed application (P1's list route moved to the
  reviewer blueprint and now needs `OPS_REVIEWER`).
- **One creation path.** `CreateClinic`, `AddDoctor` and `InviteStaff` gained `in_transaction`;
  `ApproveApplication` (`application/onboarding/approve.py`) runs them in one unit of work.
  `InviteStaffCommand.email_delivery` sends an ops invitation by email (without the owner's hourly
  limit). A failure rolls everything back; the integration test proves it with a taken slug.
- **Verification** lives on `Clinic` and `Doctor` (`verify`, `is_verified`), with the source
  in `domain/clinics/verification.py`. `has_public_page` is `ACTIVE` and verified, so the public
  page, availability, requests, proposal answers and the live token link all follow it.
- **Seed.** `make seed` verifies the demo clinics and doctors (source `OPS_CHECK` by the seeded
  ops user), makes the doctors visible with languages and a fee, gives the clinics an address and
  lists them, so P4-P7 have data. The test world's clinics are verified too.
- **Web.** `/ops/applications` and `/ops/applications/{id}` with the check form, *Reject…* and the
  *Approve* dialog (slug suggested from the name, booking mode, time zone, corrections only sent
  when changed).

Differences from the design:

- **P3 decision 7:** the reviewer does **not** see the owner's accept link. Email invitations are
  minted by the job when it sends (ADR-0016), so no link exists at approval. If the email does not
  arrive, the `send_staff_invite` job is the place to look (RUNBOOK 25).
- The invitation delivery value in the approve answer is lower-case (`email`), as the existing
  invitation answers are.

Tests (changed code only): domain (`test_clinic_application.py`), integration
`test_application_review_http.py` (AC10, AC14, R35) and `test_application_approval_http.py` (AC11-AC13,
R41), migrations `test_0033_*` and `test_0034_*`, route policies, and the unit, contract, tenancy,
seed, booking, portal and links suites (1,454 passed); web: `ReviewApplication.test.tsx` and the
ops and shell suites.

---

## M6c-P4 - Suspension and listing

Designed 26 Oct 2026; **approved in advance** (as P2). Covers FR-ONB-05 (suspension), FR-ONB-09,
FR-ONB-10. Rules: spec R50-R58.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | The one discoverability rule | `domain/clinics/listing.py`: `listing_problems(clinic, doctors)` and `is_discoverable` = listed and no problem. Problems: not `ACTIVE`, not verified, no address/city/PIN, no doctor who is active, verified, visible and has weekly hours. Used by the owner's screen now and by profiles, the sitemap and search later | A `discoverable` column kept up to date (one more thing to keep in step; the rule is cheap to compute) |
| 2 | The owner's switches | *Directory* under the owner's settings (`/settings/listing`): *Listed in the MediEase directory* (only when nothing is in the way; each problem in words) and per doctor *Show on the public page and in search* (only for an active, verified doctor). Unlisting and hiding always work | Ops lists clinics (the clinic decides whether to be found, FR-ONB-10) |
| 3 | What a problem does to a listed clinic | It stays listed but stops being discoverable until fixed; the screen says so | Unlist automatically (the owner would have to notice and list again) |
| 4 | Suspension | `OPS_ADMIN`, with a reason code (audited) and an optional note (required for *Other*, kept out of the audit). `ACTIVE` -> `SUSPENDED`; every public surface already needs `ACTIVE` | A free-text reason in the audit (free text does not belong in the audit) |
| 5 | Open requests on suspension (FR-ONB-05) | Declined by the system in the same transaction with the new reason `CLINIC_UNAVAILABLE`; the patient's in-app notice is written then (the worker cancels a suspended clinic's jobs, so no email), and the portal keeps booking notices of suspended clinics visible | Leave them to expire (patients wait hours for nothing) |
| 6 | Confirmed appointments | Not cancelled automatically: a suspension may be lifted the same day, and cancelling sends messages in the clinic's name. The RUNBOOK says to call the patients | Cancel them all (irreversible) |
| 7 | Reactivation | `OPS_ADMIN`; needs an active owner (I1). The listing is kept | Unlist on suspension |

No migration: `0034` already holds the listing columns and the decline reason. Contract 0.39.0.
Errors `CLN_LISTING_BLOCKED`, `CLN_DOCTOR_NOT_VERIFIED` (409).

### As built (M6c-P4)

Built 26 Oct 2026 as designed. `BookingRequest.withdraw`, `SuspendReason`, the listing module,
`application/clinics/listing.py` (`GetListing`, `SetListing`, `SetDoctorVisibility`,
`load_listing`), `application/ops/suspension.py`, `delivery/http/listing.py` and
`ops_suspension.py`. A doctor "has a schedule" when a weekly block is in force on the clinic's
today. Web: *Directory* (owners, `/settings/listing`), *Suspend…* and *Reactivate* on the ops
clinic list, the new decline reason in English and Hindi on the portal and as "Withdrawn while
the clinic was suspended" on the staff list. `CheckboxField` gained `disabled`.

Tests: `test_listing.py` (domain), `test_listing_suspension_http.py` (AC15, AC16, R46, R58, the
cross-clinic doctor), route policies and the cross-tenant case; the unit, tenancy and patient
notification suites (941 passed); web `DirectoryListing.test.tsx` and the ops, shell and
appointments suites.
