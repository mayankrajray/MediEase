# M6b — Patient identity, portal and booking requests: design notes

| Field | Value |
|---|---|
| Status | Opened 24 Oct 2026 after M6a merged (PR #50); plan and P1 design approved by the developer 24 Oct 2026 (A on all eight) |
| PRD | v1.2 §0 (C7, C9), §8.9, §8.13, §8.14, §13; NFR-02, NFR-10, NFR-11, NFR-18, NFR-19 |
| Specs | `docs/specs/patient-portal.md` (Draft, P1–P3, P6), `docs/specs/booking-requests.md` (written at P4) |
| ADR | ADR-0015 (patient accounts), ADR-0017 (notification service); ADR-0018 at P4 if the soft hold changes how a session's places are counted |
| Covers | FR-PRT-02..07, FR-BKG-01..08, FR-PUB-01..04, FR-REM-03, FR-QUE-06, NFR-18 |
| Issue / branch / PR | #51 · `m6b/51-patient-portal-booking` · one PR for the milestone (ADR-0011) |
| Exit criterion | A patient links clinic records by invite, prescription link or an accepted request; sees My Appointments per clinic, prescriptions, reminders and a medicine plan; requests a slot on `/c/{slug}` and the front desk accepts it from the inbox; cross-clinic isolation tests pass; `make e2e` green |
| Out of scope | Discovery and search, public doctor profiles, clinic verification and listing (M6c); patient cancel or reschedule and dependents (FR-PRT-08, 09, P1 later); data rights (FR-PRT-10); billing (M6d); WhatsApp to staff; deployment (M9) |

## Phase plan

| Phase | Builds | Requirements | Design |
|---|---|---|---|
| P1 | **Linking and the patient API.** A link between a patient account and one clinic's patient record, made by a clinic invite or by the prescription link's last-4 check; revocable by both sides. Read-only portal API for what the clinic gave the patient: linked clinics, appointments, issued prescriptions, reminders. The portal tenancy suite | FR-PRT-02, FR-PRT-03, FR-PRT-06 (b, c), NFR-18 | Below (approved 24 Oct 2026) |
| P2 | **Portal web.** The fresh dashboard with *Find a doctor*, My Appointments grouped by clinic, prescriptions (the patient page and PDF), reminders; link and unlink screens; English and Hindi; 360 px; the patient-page budget | FR-PRT-03, 04, 05, 07, NFR-02, NFR-10, NFR-11 | At its start |
| P3 | **Medicine planner.** Daily dose times derived only from each issued line's frequency, timing and days; *today* and *this course* views; optional in-app reminders | FR-REM-03 | At its start |
| P4 | **Public page and booking requests.** `/c/{slug}` with the clinic's hours, doctors and bookable slots or sessions; a request from a verified account with a short reason, a soft hold, rate limits and a cap of five open requests; `BookingRequested` to the front desk | FR-PUB-01..04, FR-BKG-01..03, 07, FR-DIS-05 (slots), NFR-19 | At its start |
| P5 | **The front-desk inbox.** Accept (match or create the patient record, link the account, create the appointment), decline with a reason, propose another slot, expiry after the response window; an expired count and the response rate for the owner | FR-BKG-04..06, 08, FR-PRT-06 (a), FR-UX-03 | At its start |
| P6 | **Patient notifications and the live token link.** In-app notifications for patients (request accepted, declined or expired; appointment confirmed, moved or cancelled; prescription ready; medicine due; follow-up due) with read state; a public "you are 3rd in line" link per appointment | FR-NTF-04, 05 (patients), FR-QUE-06 | At its start |

---

## M6b-P1 — Linking and the patient API

Proposed 24 Oct 2026; **approved by the developer 24 Oct 2026: A on all eight.** Covers FR-PRT-02, FR-PRT-03,
FR-PRT-06 (b) and (c), and NFR-18. Rules are in `docs/specs/patient-portal.md` R1–R14 (Draft).
Linking by an accepted booking request (FR-PRT-06 a) uses the same link and arrives in P5.

Facts the design rests on:

- **Accounts hold no clinic data** (ADR-0015). `patient_accounts` (Google or email and
  password, `email_verified_at`), separate cookies (`me_pt_*`, audience `mediease-portal`) and a
  `@patient` policy. Nothing connects an account to a clinic's `patients` row.
- **A clinic patient is not a person's identity.** Phones are shared by families (FR-PAT-02) and
  there is no email on a patient record, so nothing may be matched by phone or email (FR-PRT-06).
- **The prescription link** (M4-P5) names a clinic, a patient and a prescription chain. It opens
  after the last four digits of the patient's phone are entered: five wrong answers lock it, and
  only staff can reset it. Its view token lives in an HttpOnly cookie of the `/p/…` page, which
  the portal cannot read.
- **Single-use secrets.** Staff invitations and email tokens store only a SHA-256 digest of a
  256-bit secret (M1-P5, M6a-P4). Staff phone invitations show the link once with a QR code.
- **Tenancy.** Every clinic table is reached through `uow.tenant(clinic_id)`; the HTTP tenancy
  suite fails when a clinic route with an ID has no cross-clinic case. Portal routes are not
  clinic routes, so they need their own guard.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Where a link lives | A new tenant table **`patient_account_links`**: `clinic_id`, `patient_id`, `account_id`, `method` (`INVITE`, `RX_LINK`; `BOOKING` from P5), `created_at`, `created_by_user_id` (the staff member behind an invite, else null), `revoked_at`, `revoked_by` (`PATIENT` or `STAFF`). One **active** link per patient record and at most one active link per account per clinic (partial unique indexes), so a clinic record is never shared by two accounts and an account sees one record per clinic (dependents are FR-PRT-09, later). An account may be linked in many clinics. History is kept, never deleted | B: a `patient_account_id` column on `patients` (no method, no history, no revocation trail). C: allow several records per account per clinic now (dependents' consent and display rules are not designed) |
| 2 | Linking by clinic invite (FR-PRT-06 b) | On the patient's profile, staff with `PATIENTS_MANAGE` choose *Invite to the patient app*. The API makes a single-use secret (digest stored, 7 days); the link `PUBLIC_BASE_URL/portal/link/{token}` is shown **once** with a QR code, as for staff phone invitations. A new invite supersedes the old. The patient opens it signed in (or signs in or up and returns to it), sees "Link your records at *Sample Clinic* (Asha · SC-0004)" and confirms. No email verification is needed: the clinic handed over the proof | B: send the invite on WhatsApp now (a new template waiting for L-02; P6 adds it with the other patient messages). C: invite by email (patient records have no email address) |
| 3 | Linking by prescription link (FR-PRT-06 c) | The prescription page gets *Save to my MediEase*, which goes to `/portal/link/prescription/{token}`. There, **signed in with a verified account** (Google, or a verified email), the patient enters the last four digits again; the API runs the same check, under the same row lock, counters and five-try lockout as the page. This avoids sharing the page's view cookie with the portal. Because a forwarded link plus a family member's digits would pass, a link made this way is marked `RX_LINK` and shown on the patient's profile with *Unlink* | B: link silently whenever a signed-in patient opens a prescription page (the proof is weaker, and the patient never chose it). C: drop this route and rely on invites only (against FR-PRT-06) |
| 4 | What a link grants (FR-PRT-03) | Read only, for that one clinic and that one patient record: the clinic's name, phone and address; the patient's appointments (upcoming and past, every status) with doctor and place; issued prescriptions (the patient page, the latest version per chain, and the PDF); reminders with their visible status. **Never** visit notes, vitals, diagnosis, drafts, addenda, other patients, staff or audit data | B: the full visit record (FR-PRT-03 forbids notes and diagnosis) |
| 5 | Portal API | All `@patient`, under `/api/v1/portal`:<br>• `GET /links`: the account's linked clinics (clinic, the patient's first name and code, method, since);<br>• `GET /appointments`: grouped by clinic, upcoming first;<br>• `GET /prescriptions` and `GET /prescriptions/{rx_id}` (the patient page, `?lang=en\|hi`) and `/pdf`;<br>• `GET /reminders`;<br>• `GET /invites/{token}` (describe) and `POST /invites/{token}/accept`;<br>• `POST /links/prescription` (`{token, phone_last4}`);<br>• `DELETE /links/{link_id}` (unlink).<br>Staff, under the patient (`PATIENTS_MANAGE`): `POST /patients/{id}/portal-invite`, `GET /patients/{id}/portal` (linked or not, method, since, a pending invite's expiry) and `DELETE /patients/{id}/portal-link` | B: a patient-scoped copy of the staff routes (the staff bodies hold fields a patient must not see) |
| 6 | Enforcing NFR-18 | One resolver, `PortalScope`: the account's **active** links, read once per request, give the (clinic, patient) pairs; every portal read goes through `uow.tenant(clinic)` and filters by that patient. An ID in a path that is not in scope is 404 `REQ_NOT_FOUND`, never 403. A **portal tenancy suite** in `tests/tenancy/`: two accounts, two clinics, a shared phone; every `@patient` route with an ID must have a cross-account case (a guard like NFR-08's); a revoked link hides everything at once | B: check ownership in each use case by hand (one forgotten check leaks a clinic) |
| 7 | Unlinking and audit | The patient may unlink from the portal; staff may unlink from the profile. Either ends the link at once, and the record stays untouched. Audit: `patient.portal_invited` (STAFF), `patient.portal_linked` (PATIENT, with the method), `patient.portal_unlinked` (PATIENT or STAFF), `patient.portal_link_failed` for a wrong last-4 in the portal; IDs and the method only. Reading the portal is not audited, like a patient opening their own prescription page (one `patient_link.opened` per link open stays) | B: audit every portal read (noise; the patient reading their own record is not a disclosure to a third party) |
| 8 | The staff side in P1 | The patient's profile gets a small *Patient app* card: "Not linked", "Invited, link expires 31 Oct" with *Invite again*, or "Linked by invite since 24 Oct" with *Unlink*. Every role with `PATIENTS_MANAGE` sees it. No new navigation | B: a list of linked patients (no need yet; P5's inbox is where linking happens at scale) |

Fixed points:

- **Migration `0025`:** `patient_account_links`, `patient_portal_invites` (digest, clinic,
  patient, expiry, used and superseded times, created by), and the new audit actions. Both are
  tenant tables with scoped repositories and tenancy-suite cases.
- **Code.** `domain/portal/link.py` (the link and invite entities and their rules),
  `application/portal/` (linking and the read use cases, `PortalScope`), adapters, the portal and
  patient blueprints. The prescription challenge is shared with `application/links/`, not copied.
- **Contract 0.29.0.** The routes above; schemas `PortalLink`, `PortalAppointmentGroup`,
  `PortalPrescription`, `PortalReminder`, `PortalInvite`, `PatientPortalStatus`.
- **Errors:** `PRT_INVITE_INVALID` (404, unknown, used, superseded or expired: one answer),
  `PRT_ALREADY_LINKED` (409: this account already has a record in that clinic, or the record has
  another account), `PRT_UNVERIFIED_ACCOUNT` (403: a prescription link needs a verified account).
  The last-4 check reuses `LINK_CHALLENGE_FAILED` and `LINK_LOCKED`.
- **Web in P1:** only the staff *Patient app* card and the two link pages
  (`/portal/link/{token}`, `/portal/link/prescription/{token}`), so the journey can be tested;
  the portal screens themselves are P2. The prescription page's *Save to my MediEase* link stays
  within its 200 KB budget.
- **Unchanged:** the prescription page and its challenge for people without an account, every
  staff route and every existing test.

Planned verification:

- **Unit:** the link and invite rules (one active link each way, supersede, expiry, revoke); the
  scope resolver.
- **Integration (PostgreSQL):**
  - an invite links once, a second use, a superseded or expired invite is
    `PRT_INVITE_INVALID`, and a new invite replaces the old;
  - the prescription route links only a verified account, after a right last-4, and five wrong
    ones lock the link for the page too;
  - a linked account reads its clinic's appointments, issued prescriptions (never a draft, never
    notes) and reminders; after unlinking, nothing;
  - two family members sharing a phone stay apart;
  - audit rows for each change; reading writes none.
- **Tenancy suite:** account A linked in clinic A cannot read clinic B, nor another record in
  clinic A, through any `@patient` route; the guard fails when a new `@patient` route with an ID
  has no case; a staff session gets 401 on portal routes and a portal session 401 on staff routes
  (the M6a-P3 suite extended).
- **Playwright:** staff invite a patient from the profile; a new patient account opens the
  invite, links, and the API lists that clinic; failure path: a used invite says it is no longer
  valid.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### As built (M6b-P1)

Built 24 Oct 2026 to the approved design, with these details settled in the build:

- **Code.** `domain/portal/link.py` (`PatientAccountLink`, `PatientPortalInvite`, the three
  errors); `application/portal/linking.py` (staff `InviteToPortal`, `GetPortalStatus`,
  `UnlinkPatient`; patient `DescribePortalInvite`, `AcceptPortalInvite`, `LinkByPrescription`,
  `UnlinkPortal`), `application/portal/scope.py` (`PortalScope`) and
  `application/portal/records.py` (the reads); `adapters/db/portal_links.py`;
  `delivery/http/patient_portal.py` (blueprints `portal_records` and `patient_portal`).
- **One check, shared.** The last-4 comparison, counter, lockout and their audit moved from
  `VerifyChallenge` into `check_last4` (`application/links/use_cases.py`); the portal uses it
  through `ProveWithLink`, which runs the link creation in the same transaction after a right
  answer. A right answer in the portal clears the count but is not an *open* (the page was not
  shown). The PDF's render-once logic is shared the same way (`DownloadPrescriptionPdf.file_for`);
  a patient's download is not audited (decision 7A).
- **Races.** Linking locks the patient row; the partial unique indexes turn the race the lock
  cannot see (one account, two records at once) into the same `PRT_ALREADY_LINKED`.
- **Cross-clinic start.** `SqlAlchemyPortalLookup` (`uow.portal_lookup`) is the reviewed
  exception: an account's active links and an invite digest's clinic, IDs only. A suspended
  clinic's links are left out of the scope until it is active again (spec §8).
- **Audit entity.** Portal events are on the `patient` entity, so the owner's audit log shows the
  record's code; metadata holds the link or invite ID, the account ID, the method and who.
- **Responses.** Both unlink routes answer 200 with a body (the staff route the new status) like
  the other deletes, rather than 204.
- **Web.** The *Patient app* card on the profile (every role with `PATIENTS_MANAGE`), the two link
  pages under `/portal/link/…` (protected by the proxy like every portal page, so a signed-out
  visitor signs in or up and comes back), *Save to my MediEase* on the prescription page (a plain
  link, in English and Hindi; the page weighed 153 KB in the 360 px journey), and the account page
  now lists linked clinics until P2's dashboard replaces it.
- **Tests.** Unit (`tests/unit/domain/test_portal_link.py`), integration
  (`tests/integration/test_portal_linking_http.py`, AC1-AC6), the portal tenancy suite
  (`tests/tenancy/test_portal_scope.py`, with its route guard), repository scoping, HTTP
  cross-clinic cases for the three staff routes, migration `0025`, the contract
  (`tests/contract/test_portal_linking_contract.py`), web unit tests and the Playwright journey
  `e2e/portal-linking.spec.ts`.