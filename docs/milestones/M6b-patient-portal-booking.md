# M6b — Patient identity, portal and booking requests: design notes

| Field | Value |
|---|---|
| Status | Opened 24 Oct 2026 after M6a merged (PR #50); plan and P1 design approved by the developer 24 Oct 2026 (A on all eight); P1 built and confirmed (draft PR #52); P2 approved (A on all eight) and built; P3 and P3b approved and built (pushed 25 Oct 2026); P4 designed 25 Oct 2026, approved with two changes (hold override, optional age and sex) and being built |
| PRD | v1.2 §0 (C7, C9), §8.9, §8.13, §8.14, §13; NFR-02, NFR-10, NFR-11, NFR-18, NFR-19 |
| Specs | `docs/specs/patient-portal.md` (Draft, P1–P3, P6), `docs/specs/booking-requests.md` (Draft, P4) |
| ADR | ADR-0015 (patient accounts), ADR-0017 (notification service); ADR-0018 (Proposed at P4: the soft hold is the pending request, counted under the session lock) |
| Covers | FR-PRT-02..07, FR-BKG-01..08, FR-PUB-01..04, FR-REM-03, FR-QUE-06, NFR-18 |
| Issue / branch / PR | #51 · `m6b/51-patient-portal-booking` · one PR for the milestone (ADR-0011) |
| Exit criterion | A patient links clinic records by invite, prescription link or an accepted request; sees My Appointments per clinic, prescriptions, reminders and a medicine plan; requests a slot on `/c/{slug}` and the front desk accepts it from the inbox; cross-clinic isolation tests pass; `make e2e` green |
| Out of scope | Discovery and search, public doctor profiles, clinic verification and listing (M6c); patient cancel or reschedule and dependents (FR-PRT-08, 09, P1 later); data rights (FR-PRT-10); billing (M6d); WhatsApp to staff; deployment (M9) |

## Phase plan

| Phase | Builds | Requirements | Design |
|---|---|---|---|
| P1 | **Linking and the patient API.** A link between a patient account and one clinic's patient record, made by a clinic invite or by the prescription link's last-4 check; revocable by both sides. Read-only portal API for what the clinic gave the patient: linked clinics, appointments, issued prescriptions, reminders. The portal tenancy suite | FR-PRT-02, FR-PRT-03, FR-PRT-06 (b, c), NFR-18 | Below (approved 24 Oct 2026) |
| P2 | **Portal web.** The fresh dashboard with *Find a doctor*, My Appointments grouped by clinic, prescriptions (the patient page and PDF), reminders; link and unlink screens; English and Hindi; 360 px; the patient-page budget | FR-PRT-03, 04, 05, 07, NFR-02, NFR-10, NFR-11 | Below (proposed 24 Oct 2026) |
| P3 | **Prescription structure and the medicine planner.** Structured frequency patterns read against two central slot sets, the bedtime warning, explicit duration and start, new instruction codes, one medicine-plan engine (portal, PDF schedule section, patient page, P6), the *Medicines* tab and reminder preferences | FR-REM-03, FR-RX-01, 03, 04 (amended) | Below (proposed 24 Oct 2026, rewritten with the developer's decisions D1–D9) |
| P3b | **Dose tracking.** Taken and Skipped with the time marked, Not recorded derived, a 48-hour correction window, private to the patient, hidden on unlink, one-year retention under review, export and deletion | FR-REM-03 (patient side) | Below (proposed 24 Oct 2026) |
| P4 | **Public page and booking requests.** `/c/{slug}` with the clinic's hours, doctors and bookable slots or sessions; a request from a verified account with a short reason, a soft hold, rate limits and a cap of five open requests; `BookingRequested` to the front desk | FR-PUB-01..04, FR-BKG-01..03, 07, FR-DIS-05 (slots), NFR-19 | Below (proposed 25 Oct 2026) |
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

---

## M6b-P2 — Portal web

Proposed 24 Oct 2026; **approved by the developer 24 Oct 2026: A on all eight.** Covers FR-PRT-03, FR-PRT-04,
FR-PRT-05, FR-PRT-07, NFR-02, NFR-10 and NFR-11. Rules are in `docs/specs/patient-portal.md`
R15–R27 (Draft for P2). The medicine plan (FR-REM-03) is P3; booking requests in My Appointments
(`Requested`, `Declined`, `Expired`) arrive with P4 and P5; patient notifications with P6.

Facts the design rests on:

- **The P1 API is the data.** `GET /portal/links`, `/appointments` (by clinic), `/prescriptions`
  (+ page and PDF), `/reminders`, `DELETE /links/{id}`; all through `PortalScope`.
- **Portal pages cannot be server-rendered with the session.** The access cookie `me_pt_access`
  has `Path=/api/v1/portal` (ADR-0015 decision 2), so a request for `/portal/...` never carries
  it. Signed-in portal screens therefore fetch in the browser (`portalGet`, refresh once), as the
  M6a-P3 account page does. Keeping that cookie scope is worth more than server rendering.
- **The patient-page rules** (`apps/web/CLAUDE.md`): mobile-first at 360 px, < 200 KB
  transferred, no analytics SDK, strings in `src/lib/i18n/`. Today only `/p/{token}` is
  bilingual (`features/patient-link/strings.ts`); the portal is English and sits inside the
  sign-in card (`AuthFrame`).
- **Times.** The API returns UTC; the portal bodies do not yet say each clinic's time zone, so a
  slot cannot be shown on the clinic's clock (NFR-11).
- **Statuses.** Appointments carry `BOOKED`, `ARRIVED`, `IN_CONSULTATION`, `COMPLETED`,
  `CANCELLED`, `NO_SHOW`; FR-PRT-07 names `Requested`, `Confirmed`, `Declined`, `Cancelled`,
  `Completed` for the patient.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Shell and navigation | A signed-in **portal shell** apart from the sign-in card: a header (MediEase, the language switch) and a **bottom tab bar** at 360 px (a top bar from 768 px): *Home*, *Appointments*, *Prescriptions*, *Account*. P3 adds *Medicines*. The sign-in, sign-up, reset and verify pages keep `AuthFrame`. Done with route groups, so no URL changes: `/portal/(auth)/…` and `/portal/(app)/…`; the P1 link pages move into the shell | B: one long page with sections (no deep links; slow to scan once several clinics are linked). C: a hamburger drawer like staff (an extra tap for every screen on a phone) |
| 2 | Where the language lives | On the **account**: `patient_accounts.language` (`en`, `hi`; migration `0026`), changed by `PATCH /portal/me {language}` from the header switch, so it follows the person to another phone and P6's notifications can use it. Before sign-in, a `me_pt_lang` cookie (not a secret, readable by the server) chooses the auth pages' language and seeds the account's at sign-up. The prescription page in the portal opens in the account's language, with its own switch | B: the cookie only (lost on a new device; P6 would have nothing to send in). C: per linked clinic, from the record's `language` (one person, several clinics, possibly two languages; FR-PRT-10's per-clinic language is a later P1 item) |
| 3 | Budget and rendering | **Client components, held to the patient-page budget:** each portal screen's first load < 200 KB transferred at 360 px, measured in Playwright like `/p/{token}` (NFR-02's figure, applied to the portal). No new runtime dependency; strings are plain typed objects; screens load only their own data | B: a looser 300 KB for the portal (the portal is opened on the same phones as the prescription page). C: change the access cookie's path to `/` so pages can server-render (widens where the token travels; ADR-0015 chose the narrow path on purpose) |
| 4 | The fresh dashboard and *Find a doctor* (FR-PRT-05) | *Home* with nothing linked: "No appointments yet", one primary button **Find a doctor**, and a secondary "Have an invitation from your clinic?" that explains the two ways to link. Until M6c, *Find a doctor* opens `/portal/find`: search is coming; meanwhile open your clinic's own page (from P4, `/c/{slug}`) or ask the clinic for an invitation. With records: the **next appointment** (clinic, doctor, day and time or token, status), the **latest prescription**, **upcoming reminders** (next 3), and *Find a doctor* kept as a secondary action | B: hide *Find a doctor* until M6c (FR-PRT-05 makes it the first action). C: a search box over linked clinics only (looks like discovery and is not) |
| 5 | My Appointments (FR-PRT-07) | Grouped by clinic, each group with its name and phone (call button); inside, **Upcoming** then **Past** (the API's order). Each row: doctor, day and time in the **clinic's time zone** (slot) or "Token 4, morning session 10:00–13:00" (token), and a patient-facing status: `BOOKED` → *Confirmed*, `ARRIVED` / `IN_CONSULTATION` → *At the clinic*, `COMPLETED` → *Completed*, `CANCELLED` → *Cancelled*, `NO_SHOW` → *Missed*. *Requested*, *Declined* and *Expired* join with booking requests (P4, P5). Text, not colour alone | B: one list across clinics by date (FR-PRT-07 says grouped; a clinic's records must never sit among another's). C: return the patient status from the API now (P4 will reshape this list with requests anyway; the labels are the web's, in two languages) |
| 6 | Prescriptions | A list grouped by clinic (doctor, issued date, "updated" when version > 1). Opening one shows the **same patient page component** as `/p/{token}` (`PrescriptionView`, labels from the API in the chosen language, a switch), plus **Download PDF**, fetched through the portal session (refresh once) and opened as a file, never a bare link that would fail with an expired token | B: a new portal-specific layout of the prescription (two renderings of one clinical document drift apart). C: link to `/p/{token}` (the portal does not hold the token, and the last-4 check would be asked again) |
| 7 | Clinics, unlinking and reminders | *Account* holds the profile, the language, **Your clinics** (each: name, address, phone, "linked by invite since…", **Unlink** with a confirmation that says what disappears), and sign-out. Reminders appear on *Home* (upcoming) and inside each clinic group of *Appointments* (a follow-up due date with its visible status). No separate reminders tab until P3's *Medicines* | B: a *Clinics* tab (a fifth tab for a rare action). C: a reminders tab (thin until the medicine plan exists) |
| 8 | Accessibility proof (NFR-10, FR-PRT-04) | Add **`@axe-core/playwright`** (dev-only, pinned, e2e image only, never shipped) and run it on every portal screen in English and Hindi at 360 px, failing on serious or critical violations; plus the existing habits (labelled controls, focus moved to errors, text alongside colour, 44 px targets, `lang` on the page) | B: manual checks only (WCAG AA is a P1 requirement; regressions would be silent). C: axe in unit tests with jsdom (misses layout, contrast and focus order) |

Fixed points:

- **API (small).** Migration `0026`: `patient_accounts.language text not null default 'en'`
  (CHECK `en`, `hi`). `PatientAccount` gains `language`; `PATCH /portal/me {language}` changes it
  (logged as `portal.language_changed`, not audited: a display preference of the account itself,
  holding no clinic data). `PortalClinic` and `PortalAppointmentGroup` gain the clinic's `timezone`; reminders and
  prescriptions carry `clinic_id`, so the web reads the zone from the links. Contract 0.30.0.
  `GET /portal/prescriptions/{rx_id}` without `?lang` uses the account's language.
- **Strings.** `src/lib/i18n/portal.ts` (typed `en` and `hi` objects) for every portal word,
  including the P1 link pages and the sign-in pages; dates and times with `Intl` in `en-IN` and
  `hi-IN` on the clinic's zone. Known error codes get portal words in both languages; anything
  else shows the API's message and the Ref. Hindi is reviewed with the phrasebook (L-07), as for
  the prescription page.
- **Code.** `src/app/(patient)/portal/(app)/{page,appointments,prescriptions,prescriptions/[id],account,find}`
  and `(auth)/…`; `features/portal/` gains the shell, `Home`, `MyAppointments`,
  `PortalPrescriptions`, `PortalPrescription`, `PortalAccountPage`, `FindADoctor`;
  `lib/auth/portal-session.ts` gains `portalPatch` and `portalDelete`.
- **Unchanged:** every API rule of P1, the staff app, `/p/{token}` and its budget.

Planned verification:

- **Unit (Vitest):** each screen's empty, loaded, failed and ended-session states; status labels
  in both languages; the clinic's time zone on a slot and a token; grouping never mixes clinics;
  the language switch calls `PATCH /portal/me` and re-renders; unlink asks first; the PDF button
  refreshes once on an expired session.
- **API:** `PATCH /portal/me` (valid, invalid language, a staff session refused), migration
  `0026` up and down, the time zone on links and groups, the page's default language; contract.
- **Playwright (360 px):** a new account sees the fresh dashboard with *Find a doctor*; after an
  invite, Home shows the next appointment, Appointments the clinic group with *Confirmed*,
  Prescriptions opens the page and downloads the PDF; switch to Hindi and every screen is Hindi
  and stays Hindi after signing in again; unlink removes the clinic everywhere. Each screen
  < 200 KB and no horizontal overflow; axe passes in both languages. Failure path: an unlinked
  clinic's prescription URL shows "not found".
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### As built (M6b-P2)

Built 24 Oct 2026 to the approved design. Details settled in the build:

- **Routes.** `src/app/(patient)/portal/(auth)/…` (sign-in, sign-up, forgot, reset, verify; the
  card frame with a language switch reading `me_pt_lang` on the server) and `(app)/…` (`/portal`,
  `/appointments`, `/prescriptions`, `/prescriptions/[id]`, `/account`, `/find` and P1's two link
  pages). URLs did not change. The M6a-P3 account page (`PortalAccount`) is gone: *Home* and
  *Account* replace it.
- **Code.** `features/portal/PortalShell.tsx` (the account, the words and the switch for every
  screen; an ended session returns to sign-in with `next` = the current screen, R25),
  `data.ts` (one loader per screen, the portal's error words), `Rows.tsx`, `Home.tsx`,
  `MyAppointments.tsx`, `PortalPrescriptions.tsx`, `PortalAccountPage.tsx`, `FindADoctor.tsx`;
  `lib/i18n/portal.ts`; `portalPatch`, `portalDelete` and `portalPdf` in
  `lib/auth/portal-session.ts`. `PrescriptionView` gained `embedded` (an `article` inside the
  portal's `main`, so the page has one main landmark).
- **API.** Migration `0026`; `SetPortalLanguage`; sign-up's optional `language`, else the
  cookie (Google's first sign-in reads it too); `timezone` on links and groups, `phone_e164` on
  groups for the call button; the page's default language is the account's.
- **Verify banner.** Also on *Home* for an unverified password account (it gates *Save to my
  MediEase*), as well as on *Account*.
- **Measured.** First loads at 360 px: `/portal` 171 KB, `/portal/find` 169 KB,
  `/portal/appointments` 172 KB, `/portal/prescriptions` 175 KB, `/portal/account` 173 KB (all
  under 200 KB). axe (WCAG 2.1 A/AA, serious or critical) found nothing on any screen in either
  language.
- **Older journeys.** `portal-accounts`, `password-reset` and `portal-linking` now look for the
  account details under *Account* and the fresh dashboard on *Home*; what they prove is
  unchanged.
- **Emailed-link pages (follow-up commit, developer's request).** The forgot-password,
  reset-password and verify-email pages follow `me_pt_lang` too. The first two are shared with
  staff (`features/auth`): they take optional `words` (`forgotWords`, `resetWords` in
  `lib/i18n/portal.ts`), default English, so staff pages are unchanged. Every portal page is now
  bilingual. The sign-in page's `?reason=` notices and the API's own error messages stay English.

---

## Medicine planner: the developer's decisions (24 Oct 2026)

The first P3 draft (a per-code slot table, "Until the doctor says" for a missing duration, no
dose tracking) was reviewed with the developer and replaced. Settled before this design, and
not reopened below:

| # | Decision |
|---|---|
| D1 | Frequency is a **pattern** read against **two central slot sets by length**: 3 digits = morning, afternoon, night; 4 digits = morning, afternoon, evening, night. Only `0` and `1`; all-zero and any other length are refused when the doctor enters a structured frequency. Anything else (`2-0-2`, `½-0-½`, "every 6 hours") is `CUSTOM` with the doctor's words. No per-code tables anywhere |
| D2 | `BEDTIME` is shown exactly as written; the prescription editor shows a **non-blocking warning** when the pattern and bedtime may conflict. The planner never resolves the conflict; issuing is never blocked |
| D3 | Duration is **explicit**: a number of days, until review, or ongoing; an optional **start date** per prescription, default the issue date. An unspecified duration reads "Duration not stated — ask your clinic". A revision keeps its own start, date and version and never rewrites the previous one |
| D4 | Dose tracking is **M6b-P3b**: private to the patient; Taken and Skipped with the time marked; a past dose without a record is shown "Not recorded", never stored or called missed; no future doses; corrections for 48 hours; no audit row per change; nothing to analytics, logs or an LLM; hidden on unlink, deleted with the account, included in the patient's export; kept one year after the course ends (a product period, **subject to privacy and legal review**, not a claimed DPDP requirement) |
| D5 | No missed-dose advice, ever: a "Contact your clinic" action with the call button |
| D6 | Reminder **preferences** are stored in M6b (per prescription line and per active slot: on or off, and a preferred time); **delivery is P6**. Preferences never change the prescribed frequency, dose, duration or instructions. `SOS`, `ONCE` and `CUSTOM` never create reminders |
| D7 | Phases: **P3** prescription structure, the frequency engine, instruction codes, explicit duration and start, the medicine-plan API, the *Medicines* tab, reminder preferences. **P3b** dose tracking and its data lifecycle. **P4** booking requests after that |
| D8 | **One tested engine** in the domain layer; the portal, the PDF, the patient page and P6's reminders all use it; no screen interprets a frequency |
| D9 | The safety boundary stands: MediEase displays and organises the doctor's prescription; it never decides how a medicine is taken, infers an instruction, recommends a dose or resolves a contradiction |

---

## M6b-P3 — Prescription structure, the medicine-plan engine and the planner

Proposed 24 Oct 2026; **approved by the developer as written (10 points) and built** (see "As
built (M6b-P3)" below). Covers FR-REM-03 (the plan and its
reminder preferences) and the prescription-structure changes behind it (FR-RX-01, 03, 04 as
amended here). Rules are in `docs/specs/patient-portal.md` R28–R44 and, for the doctor's side,
`docs/specs/prescriptions.md` R21–R25 (both Draft for P3).

Facts the design rests on:

- **Today's frequency** is a closed list in four places: `domain/prescriptions/vocabulary.py`
  (`Frequency`: `1-0-0` … `1-1-1-1`, `SOS`, `ONCE`, `CUSTOM`), a database CHECK built from it on
  `prescription_items`, `rx_favourites` and `rx_templates`, the phrasebook's
  `frequency.<code>` words (PDF and patient page), and the staff editor (`FREQUENCIES` and the
  `BY_DIGITS` shortcuts in `features/prescriptions/vocabulary.ts`). Every stored value is already
  a valid pattern under D1, so **no stored value has to change**; only the CHECKs and the code.
- **Timing** (`BEFORE_FOOD`, `AFTER_FOOD`, `WITH_FOOD`, `EMPTY_STOMACH`, `BEDTIME`, `ANY`) and
  **preparation** codes (`SHAKE_WELL`, `DILUTE_IN_WATER` + amount, `DISSOLVE`, `CHEW`,
  `DO_NOT_CRUSH`, `CUSTOM` + text) are already separate from frequency; with-water, warm-water
  and milk are missing.
- **Duration** is `duration_days` (1–365) or null; null means "not stated". There is no start date:
  everything assumes the issue day.
- **Immutability.** Issued versions never change (a database trigger), and each version's PDF is
  rendered once and stored (prescriptions R18). A new PDF layout therefore applies to versions
  issued after it ships; stored PDFs stay as they were.

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | The engine | `domain/prescriptions/schedule.py`: `Slot` (`MORNING`, `AFTERNOON`, `EVENING`, `NIGHT`), **`SLOT_SETS = {3: (MORNING, AFTERNOON, NIGHT), 4: (MORNING, AFTERNOON, EVENING, NIGHT)}`**, `FrequencyPattern.parse()` (canonical `1-0-1`; the rules of D1), `Frequency` = a pattern or `SOS` / `ONCE` / `CUSTOM`, and `schedule_of(item)` → the line's slots (empty for the three non-patterns) and whether it may be reminded. `plan.py` builds a day or a course from it. The phrasebook words a pattern from its slots (*"Morning and night"*, *"सुबह और रात"*) instead of a phrase per code, so the PDF, the patient page and the plan say the same thing | B: keep the code list and add entries (the per-code table D1 rules out). C: a bit mask column (unreadable in data, logs and support) |
| 2 | How the staff editor learns what a pattern means | The API publishes the slot sets and the instruction vocabulary once, **`GET /api/v1/rx-vocabulary`** (slot sets with their words, timing, preparation and storage codes, duration kinds), cached for the session; the editor validates and labels typed patterns from that data and every saved line comes back with the engine's `slots`. A web test fails if a slot table literal appears in `src/` | B: a preview call per keystroke (latency while typing). C: keep a copy of the sets in the web (the drift D8 forbids) |
| 3 | Bedtime warning (D2) | The engine returns `warnings` on each draft line, shown under the line and in *Review and issue*, never blocking: **`BEDTIME_WITHOUT_NIGHT`** when timing is `BEDTIME` and the pattern has no night dose, **`BEDTIME_WITH_OTHER_SLOTS`** when it has night and other slots too, and `BEDTIME_UNTIMED` for `SOS`/`ONCE`/`CUSTOM` with bedtime. Wording: "Check: 'at bedtime' with this frequency — is that what you mean?" The issued document shows exactly what the doctor wrote | B: warn only when there is no night dose (misses `1-0-1` + bedtime, the commonest ambiguity). C: block issue (D2 says never) |
| 4 | Duration (D3) | `duration_kind` per line: `DAYS` (with `duration_days` 1–365), `UNTIL_REVIEW`, `ONGOING`, or **null = not stated**. Existing rows: `DAYS` where `duration_days` is set, else null. Words: "5 days" / "Until your next review" / "Ongoing — as prescribed" / "Duration not stated — ask your clinic". `UNTIL_REVIEW` never reads the follow-up date to make an end (that would be inference). Favourites and templates gain the same field | B: keep null meaning "until the doctor says" (D3 rules out). C: a free-text duration (no course to plan) |
| 5 | Start date (D3) | `prescriptions.starts_on` (date, clinic calendar). In a draft it is optional; at issue it is set to the issue day when empty; the doctor may choose from 30 days before to 30 days after the issue day. A **revision's draft starts empty**, and the editor shows the previous version's start beside it ("Previous version started 12 Oct — keep that date?") so continuing a course is the doctor's choice, never automatic. Existing issued rows are backfilled to their issue day in the clinic's zone by the migration | B: copy the previous start into the revision (silently continues a course the doctor may have restarted). C: a start per line (heavier to write; the PRD has no case for it yet) |
| 6 | Instruction codes | Preparation gains `WITH_WATER`, `WITH_WARM_WATER`, `WITH_MILK` (the doctor picks them like the others; the system never adds one). "Mix in water", "shake well", "take at bedtime" and the doctor's own instruction already exist. The plan, PDF and page show **when** (slots, food timing) and **how** (preparation) as separate fields | B: let the system suggest instructions by medicine (D9 rules out). C: a free-text field only (loses the patient's Hindi wording) |
| 7 | The plan API and the day | `GET /portal/medicine-plan?date=` (default today, ±30 days, else 422): per linked record's **current** versions, each line's entries for the day with slot, scheduled time, medicine, dose, food timing, preparation, duration words and "day N of M" (for `DAYS`), the prescription's doctor, clinic, issue date and start; untimed lines (`SOS`, `ONCE`, `CUSTOM`) in a separate "As the doctor wrote" list. A course is shown from its start; `DAYS` ends after M days; `UNTIL_REVIEW`, `ONGOING` and not-stated lines show while their version is current (any other end would be invented). `GET /portal/medicine-plan/courses`: the same per prescription, with ended `DAYS` courses for 7 days. **Scheduled times** come from the account's daily slot times (defaults 08:00, 14:00, 18:00, 21:00; each 05:00–23:30, increasing; migration `0027`), changed under *Account* | B: per-prescription times (four times to set per visit). C: hide open-ended lines after N days (an invented end) |
| 8 | Reminder preferences (D6) | Table `medicine_reminder_prefs` (tenant data): clinic, patient, account, the **prescription version** and line, slot, `enabled`, `remind_at` (null = the slot's time). Created only for lines with slots; `PUT /portal/medicine-plan/reminders` takes `{prescription_id, item_id, slot, enabled, remind_at}`; refused (422) for an untimed line or a slot the line does not have. A **revision does not inherit** preferences (its lines may differ); the patient is told "This prescription was updated — set your reminders again". Cleared when the link ends. Stored only; P6 delivers | B: per prescription only (D6 asks per line and slot). C: inherit across revisions by medicine name (matching medicines is an inference) |
| 9 | The *Medicines* tab | A fifth tab. *Today*: Morning, Afternoon, Evening, Night (each with its time), then "As the doctor wrote"; each entry: medicine and dose as written, food timing, how to give, "Day 3 of 5" or the duration words, clinic and doctor, and the reminder switch and time. *Courses*: per prescription. The same medicine on two prescriptions is two entries (D9). Every planner screen: "This plan only lays out your prescription. If anything is unclear, ask your doctor." with *Contact your clinic* (call) | B: a week grid (budget). C: merge or sort by medicine (implies equivalence) |
| 10 | PDF and patient page | A **Medicine schedule** section (`layout_version` 2): one row per line — medicine, dose, a mark per slot of its set (or "As the doctor wrote: …"), food timing, how to give, duration — built from the engine and phrasebook only, under the existing medicine cards, in the prescription's language. The patient page shows the same table. Applies to versions issued after release; stored PDFs are not re-rendered | B: replace the medicine cards (loses warnings and notes laid out per line). C: re-render old PDFs (breaks render-once and their record value) |

Fixed points:

- **Migration `0027`:** frequency CHECKs → a pattern CHECK
  (`^[01](-[01]){2,3}$`, not all zeros, or `SOS`/`ONCE`/`CUSTOM`) on `prescription_items`,
  `rx_favourites`, `rx_templates`; `duration_kind` on the three (backfilled); preparation codes;
  `prescriptions.starts_on` (backfilled for issued rows); the account's four slot times;
  `medicine_reminder_prefs`. Expand-only; down reverses (refused while new values exist, like
  earlier enum widenings).
- **Contract 0.31.0:** `Frequency` becomes a pattern string (with the three words); items gain
  `duration_kind`, `slots`, `warnings`; prescriptions `starts_on`; `GET /rx-vocabulary`;
  `GET /portal/medicine-plan`, `/courses`, `PUT /portal/medicine-plan/reminders`; the account's
  slot times on `PATCH /portal/me`.
- **Audit:** prescription changes keep their existing audit; nothing new for the planner's reads
  or the patient's preferences (logged with IDs, never medicine names).
- **Unchanged:** issued prescriptions and their PDFs, the last-4 page flow, P1 and P2 rules.

Planned verification:

- **Engine (unit, the core of the phase):** every 3- and 4-digit 0/1 pattern (generated, not
  listed) maps to its slots in order; all-zero, 2- and 5-digit, `2-0-2`, `½-0-½`, spaces and
  letters refused for a structured frequency; `SOS`/`ONCE`/`CUSTOM` have no slots and no
  reminders; the three bedtime warnings and no warning otherwise; duration words for the four
  kinds; a course's day count on the clinic's calendar from `starts_on`; a revision's plan
  replaces its predecessor's and leaves it untouched.
- **API:** the plan only for linked records (portal tenancy suite cases for the new routes),
  untimed lines apart, the reminder preference rules, `starts_on` validation and backfill, the
  pattern CHECKs, migration `0027` up and down, contract, staff draft responses with `slots` and
  `warnings`.
- **Web:** the editor accepts `110`, `1011` and refuses `000`, `20`; labels come from
  `/rx-vocabulary`; the bedtime warning shows and does not block; duration kind and start in the
  editor and review; *Medicines* in both languages; reminder switches only on timed lines.
- **PDF:** the schedule section for a 3- and a 4-slot line, an untimed line and each duration
  kind, in English and Hindi; a stored v1 PDF is byte-identical after release.
- **Playwright (360 px):** the doctor writes `1-1-0` after food for 5 days and `SOS`, sees the
  schedule in review, issues; the linked patient sees Morning and Afternoon "Day 1 of 5" and the
  SOS line under "As the doctor wrote" with no switch; turns a reminder on at 07:30 and it stays
  after reload; under 200 KB and axe-clean in both languages. Failure path: entering `0-0-0`
  shows the editor's error and saves nothing.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### As built (M6b-P3)

Built 25 Oct 2026 to the approved design. Changes from it, and details settled in the build:

- **No backfill (deviation from points 4 and 5).** Issued rows cannot be updated: the
  `prescriptions_immutable` and `prescription_items_frozen` triggers compare whole rows. So
  migration `0027` adds `duration_kind` and `starts_on` as nullable columns and writes nothing.
  A row with `duration_days` and no kind reads as `DAYS` (repository and `item_from_json`); a
  null `starts_on` is the issue day on the clinic's calendar (`plan.course_start`), and issuing
  leaves it null rather than writing the day. The CHECK is `duration_kind IS NULL OR
  (duration_kind = 'DAYS') = (duration_days IS NOT NULL)`.
- **Favourites and templates** keep their lines as JSONB, so no CHECK changed there; their lines
  carry `duration_kind` through `item_json`.
- **Names.** The engine's notes on a line are `line_warnings` in the API (`warnings` is already
  the doctor's own text). `medicine_reminder_prefs.item_id` has **no foreign key**: an issued
  version's items can never be deleted, and a key would stand in front of AC1's TRUNCATE trigger
  check. The unique key is `uq_medicine_reminder_prefs_line_slot` (the column-named default
  passes 63 characters).
- **Wording.** A pattern is worded from its slots, so `1-1-1` now reads "Three times a day,
  morning, afternoon and night" and `1-1-1-1` names its four slots; `1-0-0`, `0-0-1` and `1-0-1`
  read as before. A line with no frequency shows "Times not stated — ask your clinic" in the
  schedule.
- **Layout 2 only.** The schedule section and "Duration not stated — ask your clinic" appear only
  on versions issued on layout 2 (`document.SCHEDULE_LAYOUT`); a layout-1 version keeps its
  words. A test pins the SHA-256 of layout 1's three files. The PDF marks a slot with "•" and an
  empty one with "—" (the vendored Noto Sans has no check mark).
- **Editor.** The entry row's *Days* field also takes `R` (until review) and `G` (ongoing); *More*
  has a frequency text field read the same way and a *How long* choice. *Course starts on* sits
  under follow-up, with the revised version's start as a hint. *Review and issue* lists the
  notes and shows the schedule table. Until `/rx-vocabulary` has loaded, a typed pattern only shows the field's hint (the words S, O and C work at once); the row is not held, which a timing-dependent test caught in P3b.
- **Portal.** The patient page shows the schedule as a list per medicine (a table does not fit
  360 px). Reminder controls are on *Courses* only; *Today* says "Reminder on at 07:30". A
  changed time is saved with *Save time* (a time picker gives no reliable blur), and the screen
  says reminders are sent in a later update. `PATCH /portal/me` takes `language`,
  `slot_times` or both (`SetPortalLanguage` kept its name). *Today* is the first linked clinic's
  calendar day (the pilot is one zone). The five tabs are as wide as their words, so
  "Prescriptions" no longer breaks at 360 px.
- **Access.** `/rx-vocabulary` is `CLINICAL_VIEW`. The plan routes take no ID in the path, so the
  portal suite has a separate cross-account case for the plan, the courses and a reminder choice.
- **Measured.** First loads at 360 px: `/portal/medicines` 180 KB, `/portal/account` 177 KB;
  axe found nothing serious in English or Hindi. The e2e journey sets the reminder time with the
  input's prototype setter: Playwright's `fill` on a time input is not seen by React.
- **Gates.** API 1943 tests, 97.50% coverage; web 598; Playwright 35/35; smoke passed.

---

## M6b-P3b — Dose tracking and its data lifecycle

Proposed 24 Oct 2026; **approved by the developer as written (7 points) and built** (see "As
built (M6b-P3b)" below; with P3; built after it). Covers
FR-REM-03's patient side under decisions D4 and D5. Rules: `docs/specs/patient-portal.md`
R45–R54 (Draft for P3b).

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | What is stored | Table `dose_records` (tenant data, its own scoped repository): clinic, patient, account, **prescription version** and line, `on_date`, `slot`, `state` (`TAKEN` \| `SKIPPED`), `marked_at`, `created_at`, `updated_at`; unique per account, version, line, date and slot. Nothing for a dose not marked: "Not recorded" is derived when the dose's time has passed. No reason field, no free text | B: store "missed" rows by a job (D4 forbids storing or inferring missed). C: a reason picker ("forgot", "side effect") (clinical inference and sensitive data the PRD does not need) |
| 2 | What can be marked | Only scheduled entries of the plan (timed lines, inside the course), from the dose's day at 00:00 clinic time until **48 hours after its scheduled time**; never a future day, never untimed lines. Changing Taken ↔ Skipped or clearing a mark follows the same window; after it the record is read-only | B: any time (the record stops meaning "at the time"). C: until the scheduled time only (a late dose could never be recorded) |
| 3 | Who sees it | **Only the patient account**, through `PortalScope` like every portal read. No staff route, no ops route, no clinic report; the tenancy suites gain cases proving staff and ops cannot reach it. Sharing with a clinic would be a later, explicit, per-clinic opt-in with its own design (and counsel, L-04) | B: visible to the clinic now (D4 says private by default) |
| 4 | Privacy in code | No audit rows (D4); log events carry counts and IDs only (`dose.marked count=1`), never a state, medicine or time; the record is excluded from every log context by a test; no analytics exist and none may read it; not sent to any model. Classified as **C3 health data** in SECURITY_AND_COMPLIANCE.md | B: audit each mark (D4 rules out; also floods the table) |
| 5 | Lifecycle | **Unlink:** hidden at once (the scope no longer reaches it); kept, so a relink of the same account and record shows it again. **Retention:** the purge job deletes records one year after the course end (`DAYS`), or one year after the dose date for open-ended courses — a product period, recorded as **subject to privacy and legal review**. **Account deletion and export:** FR-PRT-10 is not built yet; P3b adds the repository's `delete_for_account` and `export_for_account` and tests them, and the RUNBOOK says how support runs both on request until the portal's own data-rights screens exist (FR-PRT-10) | B: delete on unlink (a mis-tap would erase a patient's history). C: build the whole FR-PRT-10 now (outside M6b's scope) |
| 6 | What the patient sees | On *Today*, each timed entry gets **Taken** / **Skipped** buttons (and *Change* within the window), its state in words with the time marked ("Taken at 08:12"). A *History* view per course: each day and slot as Taken, Skipped, Not recorded or Upcoming; counts per state for the course. For Not recorded and Skipped only: "If you are unsure what to do, contact your clinic" with the call button — no other advice, ever | B: a percentage "adherence score" (a judgement on the patient) |
| 7 | Revisions | Records stay on the version and line they were made for; a revision starts a new plan with no records. History shows each version's course separately, newest first | B: carry records to the revision (lines may differ; would rewrite history) |

Fixed points: migration `0028` (`dose_records`); contract 0.32.0 (`PUT`/`DELETE
/portal/medicine-plan/doses`, `GET /portal/medicine-plan/history?prescription_id=`); the
retention purge counts `dose_records`; DATA_MODEL, SECURITY_AND_COMPLIANCE (C3, retention under
review) and RUNBOOK (export and deletion on request).

Planned verification: the window (before the dose's day, after 48 hours, a future day refused;
untimed refused), Not recorded derived and never stored, unlink hides and relink shows, the
purge at one year, export and delete for an account, staff/ops cannot reach it (tenancy), no
state in any log line (a log-capture test), Playwright: mark Taken, change to Skipped, see the
history and the Contact your clinic action; axe and budget.

### As built (M6b-P3b)

Built 25 Oct 2026 to the approved design. Details settled in the build:

- **Storage.** Migration `0028`: `dose_records` (tenant), unique per account, version, line, day
  and slot (`uq_dose_records_dose`); `item_id` has no foreign key, as for reminder choices.
  Each row carries **`keep_until`**, set when the dose is marked (course end, or the dose's day
  for an open-ended line, plus 365 days), so the daily purge deletes by that date alone, like its
  other tables; the retention audit row gains a `dose_records` count.
- **API.** `PUT /portal/medicine-plan/doses` (Taken or Skipped; marking again changes the state
  and the time marked), `DELETE` with the same four query parameters (clears it), `GET
  /portal/medicine-plan/history?prescription_id=` (an issued or superseded version; newest day
  first, at most 60 days back; counts per state; the chain's versions). Outside the window is
  409 **`PRT_DOSE_NOT_MARKABLE`**; an untimed line, a slot the line lacks or a day outside the
  course is 422. The plan's timed entries gain **`mark`** (status, time marked, markable) and
  every entry the clinic's `timezone`; the field could not be called `dose`, which is the
  doctor's dose. Contract 0.32.0.
- **Window.** A dose is due at the person's slot time on its day, on the clinic's clock; it can be
  marked from 00:00 that day until 48 hours after (`domain/portal/doses.py`). Not recorded and
  Upcoming are computed on read and never stored.
- **Privacy.** No audit row per mark; `dose.marked` and `dose.cleared` log the account, the
  prescription and a count. `tests/tenancy/test_dose_privacy.py` fails if any module other than
  the patient's own use cases calls the repository, or anything but the support command calls
  the cross-clinic `dose_lifecycle`; staff reads of the same patient carry no marks.
- **Export and deletion (R54).** `make dose-data ARGS="export <account> --out
  /exports/<account>.json"` writes a new owner-only file under `.exports/` (gitignored; the JSON
  never goes to the terminal, which carries the logs); `ARGS="delete <account> --confirm"`
  deletes. RUNBOOK §"Dose records on request". They log IDs and counts; they write no audit row
  (no clinic owns the request) — to revisit with FR-PRT-10.
- **Web.** *Today*: Taken / Skipped on each timed entry, then the state with the time marked on
  the clinic's clock and *Change* (Taken, Skipped, *Clear the mark*) while the window is open; for
  Skipped and Not recorded only "If you are unsure what to do, contact your clinic." with the
  call; a line saying only the patient sees the marks. *Courses*: *History* per course with counts
  and a switch between versions. English and Hindi.
- **Measured.** `/portal/medicines` with marks 181 KB at 360 px; axe found nothing serious.

---

## M6b-P4 — The public page and booking requests with a soft hold

Proposed 25 Oct 2026; **approved by the developer 25 Oct 2026 with two changes:** (1) staff may
override a hold, only through an explicit, confirmed, audited action (spec R18a); (2) phone stays
required, age and sex stay but are optional unless the clinic requires them (R12). The developer
also fixed the two clocks: a **2-hour hold** (30 minutes to 8 hours) protects the slot; the
**request** may stay open up to **4 hours** (or until 1 hour before the slot), and once the hold
ends the slot is bookable again while the request stays pending until its deadline. Where point 4
below says staff are refused, read R18 and R18a. Covers FR-PUB-01..04, FR-BKG-01..03
and 07, FR-DIS-05 (the slots a patient sees) and NFR-17, NFR-19. Rules:
`docs/specs/booking-requests.md` R1–R30 (Draft). The hold model is ADR-0018 (Proposed). P5
(accept, decline, propose, expiry, linking) is not designed here; P4 leaves room for it.

Facts the design rests on:

- **The slug exists** (`clinics.slug`, unique, 3–63 lower-case words, not editable since M1) but
  nothing public uses it. The comments saying "public URLs from M7" are stale.
- **No "verified" or "listed" state.** A clinic is `ONBOARDING`, `ACTIVE` or `SUSPENDED`;
  verification and listing are M6c (FR-ONB, FR-DIS). There are no clinic hours, map link, fee
  or languages: hours exist only as each doctor's weekly blocks and exceptions.
- **Availability** is computed for staff only (`GET /sessions`, `APPOINTMENTS_MANAGE`); reading
  it **materialises** the date's sessions (generate-on-read). Capacity is `capacity −
  booked_count`, kept under the session's `FOR UPDATE` lock; slots taken are the active
  appointments' `slot_start`. There is **no hold concept** anywhere, and `reconcile` retires an
  unbooked session (`booked_count == 0`).
- **Patient accounts have no phone** and no age or sex. FR-BKG-01 asks for the contact phone
  "from the verified patient account"; no OTP by decision (PRD §0). Verified = Google, or a
  confirmed email (FR-PUB-03, ADR-0015).
- **Staff notifications** are typed kinds through the notification service (ADR-0017); a request
  has no clinic patient record yet, so `PatientRef` (first name · code) does not apply.
- **Rate limits** exist (`public_rate_limits`, minute and hour windows; IP hashed).

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | Who has a page (FR-PUB-01, NFR-19) | One domain rule, **`Clinic.has_public_page`**: `ACTIVE` until M6c adds verification, when it becomes `ACTIVE ∧ verified` in that one place. An unknown slug, an `ONBOARDING` or `SUSPENDED` clinic: the identical 404 on the page, its availability and a request. Listing in the directory is M6c and independent (FR-DIS-07) | B: a `verified` flag now with no process behind it (a checkbox nobody owns). C: wait for M6c (P4 could not be tried) |
| 2 | What the page shows (FR-PUB-01, NFR-17) | Only published fields, from one allow-listed body: clinic name, address, city, state, pincode, phone (a call button), a **map link built from the address** (a maps search URL, no coordinates), **hours** derived from the doctors' active weekly blocks ("Mon–Sat 10:00–13:00" per doctor and for the clinic), and each active doctor's display name, qualification and specialty. No registration number, staff, patient or count. A test fails if the body gains a field outside the allow-list | B: new clinic fields for hours, map and fee (an editor and a migration for data the schedule already holds). C: show registration numbers (not needed to book; FR-DIS wording is counsel's, L-04) |
| 3 | The slots a patient sees (FR-DIS-05) | `GET /public/clinics/{slug}/availability?doctor_id=&from=` → the next **14 days**: in slot mode the free slots (the plan, minus booked slots and **live holds**), in token mode each session with "places left" (never a token number). From **1 hour ahead** (FR-BKG-06's "1 hour before the slot"). Computed **without writing** (the doctor's plan merged with existing rows); the session row is created only when a request is made. Exceptions and leave apply as for staff | B: reuse generate-on-read (a public GET writing rows). C: 30 days (more load, little use before a response window of hours) |
| 4 | The soft hold (FR-BKG-02; ADR-0018) | A request **is** the hold: `booking_requests` rows with `hold_expires_at` (created + the clinic's `request_hold_minutes`, default 120, 30–480). A hold is live while the request is `PENDING` and `hold_expires_at > now`; nothing has to run for a hold to lapse. Under the session's `FOR UPDATE` lock, places = `capacity − booked_count − live holds`, and a held slot counts as taken. Staff booking into a held slot or a session's last held place is refused **`APT_SLOT_HELD`** (409, "held for an online request until 14:30"); P5 lets staff decline the request. `reconcile` treats a session with live holds like a booked one (closed, never retired) | B: a `held_count` column on `sessions` (needs a job to decrement on time, and drifts). C: no hold, first accept wins (two patients told "requested" for one slot) |
| 5 | Identity and contact (FR-PUB-03, FR-BKG-01) | `@patient` with a **verified** account, else 403 `PRT_UNVERIFIED_ACCOUNT` (P1's). The form asks the **contact phone** (Indian mobile, normalised to E.164, not verified: no OTP by decision), **age in years** and **sex** (or "prefer not to say") so P5 can match or create the record without a call; the name is the account's. They are stored on the request, never on the account, and the form is prefilled from the account's last request. The request is for the account holder only (dependents are FR-PRT-09) | B: a phone on the account (a field the portal does not otherwise need; one place to change it). C: ask nothing and let front desk phone the patient (FR-BKG-01 names the phone) |
| 6 | The reason (FR-BKG-01) | Optional free text, 1–200 characters, under a visible notice in the page's language: "Not for emergencies. In an emergency call 112 or go to the nearest hospital." Treated as **clinical (C3)**: never in a log, a notification title or an error | B: a list of reasons (the clinic, not MediEase, knows its services). C: required (a patient may not want to say) |
| 7 | Abuse controls (FR-BKG-07, NFR-19) | Per **account** 5 requests an hour; per **IP** 20 an hour (hashed, as today); per **phone** 5 a day; at most **5 open** (`PENDING`) requests per account (`PRT_TOO_MANY_REQUESTS`, 409) and **one open request per account per session** (`PRT_REQUEST_EXISTS`, 409). Over a limit: 429 `PRT_RATE_LIMITED` with `Retry-After`. The page and availability: 60 reads a minute per IP. No automatic ban; the no-show counter is shown to staff with the request in P5 | B: CAPTCHA (a third-party script on a 200 KB page). C: per-IP only (shared Wi-Fi and phones) |
| 8 | Who is told (FR-BKG-03) | Event **`BookingRequested`**; the notification service writes an in-app notification **`booking.requested`** to the clinic's front desk and owners (and the doctor, by preference, default off): "New request · Asha · 26 Oct, 10:30 with Dr. Sample" — the account's first name (no code yet) and the place, never the reason. Links to the staff **Booking requests** list. WhatsApp to staff is out of scope for M6b | B: notify every member (doctors with full queues). C: email (ADR-0016 port, but no staff ask for it) |
| 9 | What staff see in P4 | A read-only **Booking requests** list (front desk, owners, doctors for their own) of `PENDING` requests: who (name, age, sex, phone), doctor, place, reason, received and "held until". Actions arrive in P5. Held slots show as **Held** on the staff session view and the booking form refuses them (point 4) | B: nothing until P5 (notifications would point nowhere). C: build the actions now (that is P5) |
| 10 | The patient's side (FR-PUB-04, FR-PRT-07) | `/c/{slug}` (public, English and Hindi with the portal's switch, 360 px, < 200 KB, axe): the clinic, hours, doctors and *Request an appointment*: doctor → day → slot or session → sign in or up if needed and **return to the same choice** (FR-DIS-08) → the form → "Requested. The clinic will confirm or suggest another time." *My Appointments* lists the request as **Requested** under that clinic (even before any link). Sharing: *Share on WhatsApp* (`wa.me/?text=`) and *Copy link*, with Open Graph tags (name and address only). The page stays `noindex` until M6c and counsel (FR-DIS-06, L-04). Owners see the page's link with *Copy* in clinic settings, beside the hold time | B: index now (doctor-listing wording is unreviewed). C: a page with a guest form (FR-PUB-03 forbids guests) |

Fixed points:

- **Migration `0029`:** `booking_requests` (tenant: clinic, doctor, session, `slot_start` null in
  token mode, account, contact phone, age, sex, reason, `status` `PENDING` (P5 adds `ACCEPTED`,
  `DECLINED`, `EXPIRED`, `CANCELLED`, `PROPOSED`), `hold_expires_at`, `created_at`); a partial
  unique index on `(session_id, slot_start)` for live `PENDING` rows in slot mode and on
  `(account_id, session_id)` for `PENDING`; `clinics.request_hold_minutes`. No patient record
  until P5.
- **Contract 0.33.0:** `GET /public/clinics/{slug}`, `GET /public/clinics/{slug}/availability`,
  `POST /portal/booking-requests`, `GET /portal/booking-requests`, `GET /booking-requests`
  (staff, read-only), the hold time on the clinic settings; `PortalAppointmentGroup` gains
  `requests`.
- **Errors:** `APT_SLOT_HELD` (409), `PRT_TOO_MANY_REQUESTS` (409), `PRT_REQUEST_EXISTS` (409),
  `PRT_RATE_LIMITED` (429); a slot taken or held meanwhile is `APT_SLOT_TAKEN` /
  `APT_SESSION_FULL` (409) as for staff.
- **Audit:** `booking_request.created` (PATIENT; IDs, doctor, place; no phone, reason or age).
  Page and availability reads are not audited.
- **Tenancy:** the slug lookup is a named platform reader returning published fields only
  (`SqlAlchemyPublicClinicReader`, ADR-0003); everything else through `uow.tenant`. The portal
  suite gains cross-account cases; the HTTP suite proves clinic B never sees A's requests.
- **Unchanged:** staff booking except the hold refusal; P1–P3b.

Planned verification:

- **Unit:** `has_public_page`; hours from blocks; availability = plan − booked − live holds
  (slot and token modes, leave, 1-hour lead, 14 days); a lapsed hold frees the place with no
  job; reconcile keeps a held session; the request rules and limits.
- **API:** the identical 404s (NFR-19); the allow-list (NFR-17: no field outside it, no staff or
  patient data); two accounts requesting one slot in parallel → one 201, one 409 (AC1-style);
  staff booking a held slot → `APT_SLOT_HELD`, after the hold lapses → booked; the limits and
  the cap; unverified → 403; logs and notifications without phone, reason or age; migration
  `0029`; contract; tenancy.
- **Web:** the page and the request flow in both languages; return to the same slot after
  sign-in; *Requested* in My Appointments; the staff list and the held slot.
- **Playwright (360 px):** a signed-in patient opens `/c/sample-clinic`, picks a slot, requests
  it; front desk gets the notification and sees it in the list and as Held; a second account
  cannot request that slot. Failure path: an unknown slug shows the same "not found" as a
  suspended clinic. Budget and axe on the page and the form.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.

### As built (M6b-P4)

Built 26 Oct 2026 to the approved design (with the developer's two changes). Details settled in
the build, and the places where it differs from the spec:

- **Storage.** Migration `0029`: `booking_requests` (tenant) and two clinic settings,
  `request_hold_minutes` (30-480, default 120) and `request_requires_age_sex` (default false). The
  partial unique index `uq_booking_requests_account_session_pending` allows one open request per
  account and session; there is **no unique index per slot** (ADR-0018). The notification kind
  CHECKs gain `booking.requested`.
- **Page rule.** `Clinic.has_public_page` (today: `ACTIVE`). An unknown slug and a clinic without
  a page are the same 404 `REQ_NOT_FOUND`; the body is an allow-list (`CLINIC_FIELDS`,
  `DOCTOR_FIELDS`) and a test fails on any other key.
- **Availability** (`GET /public/clinics/{slug}/availability`) is computed without writing: the
  plan minus booked slots and live holds, from now + 2 hours, 14 days. A session or day with
  nothing left to ask for is **left out**, not shown as 0 left.
- **The hold** is a `PENDING` request with `hold_expires_at > now`, counted under the session's
  `FOR UPDATE` lock by requests, staff booking, reschedule and walk-ins. It lapses by time alone;
  no job. `hold_expires_at = min(now + request_hold_minutes, respond_by)` and
  `respond_by = min(now + 4h, slot - 1h)`. `reconcile` keeps a session that has a pending request
  (closed, never deleted).
- **Override (R18a).** `override_hold: true` on `POST /appointments` and `/reschedule`. Without
  it a held time is 409 `APT_SLOT_HELD` (`held_until`, `first_name`). With it the blocking hold
  ends in the same transaction (`hold_overridden_at/by`) and `appointment.hold_overridden` is
  audited (STAFF; IDs only); the request stays `PENDING`. In token mode, if places are free but
  all held, the newest hold ends. The drawer asks first ("Book anyway (override the patient's
  request)") and also handles a hold that appeared while it was open.
- **Request.** `POST /portal/booking-requests` needs a verified account (`PRT_UNVERIFIED_ACCOUNT`).
  Phone is required; age and sex are optional unless the clinic requires them; the reason is
  optional, up to 200 characters, and is never logged, audited or notified. The staff
  notification (`booking.requested`, owners and front desk) names the first name and the place
  only. Limits: 5 an hour per account, 20 an hour per address, 5 a day per phone, 5 open across
  clinics, one per account and session; 429 `PRT_RATE_LIMITED` with `Retry-After`.
- **Web.** `/c/{slug}` (server-rendered, English and Hindi, `noindex`, Open Graph with name and
  place only, call, directions, share and copy); choosing a time goes to
  `/portal/request?clinic=&doctor=&session=&slot=`, so signing in returns to the same time. The
  portal's session-ended redirect now keeps the query string. *My appointments* lists requests as
  "Requested" (also for unlinked clinics). Staff: *Booking requests* list (owner and front desk
  nav; doctors reach it by URL), *Held* in the booking drawer, and *Online booking requests* in
  schedule settings (page link with Copy, hold time, ask age and sex).
- **Measured at 360 px** (first load, fresh browser): `/c/sample-clinic` 173 KB,
  `/portal/request` 183 KB, `/portal/appointments` 180 KB; axe found nothing serious.

Differences from the spec (all deliberate):

- Hours are per doctor only (weekly blocks); the spec's clinic-level hours do not exist.
- No `SqlAlchemyPublicClinicReader`: the use case reads `uow.clinics.get_by_slug` and builds the
  allow-listed body.
- The 4-hour response window is a constant (`RESPONSE_WINDOW`), not a setting; P5 may add one.
- The session is named by its start (`session_start`), not an ID, because availability writes
  nothing and the session may not exist yet.
- The per-phone limit counts real requests (`count_for_phone`) rather than a rate-limit bucket,
  because that table keeps windows for an hour and a phone number never belongs in a bucket name.
- Doctors are not notified of requests in P4 (owners and front desk only), and doctors see every
  pending request through the API, as for the rest of the schedule.

Known limits to carry forward:

- **The caller's address is the web server's** until a reverse proxy we control sets
  `X-Forwarded-For` (ARCHITECTURE A11, M6-P1 of deployment). The page-read limit (60 a minute) and
  the per-address request limit (20 an hour) therefore apply to *all* patients together in the
  pilot. RUNBOOK 24 says what to do if they trip.
- A suspended-clinic page is covered by the API test (identical 404), not by a browser journey.

---

## M6b-P5 - The front-desk inbox: accept, decline, propose, expiry

Proposed 26 Oct 2026; **approved by the developer 26 Oct 2026** with two clarifications: (A) exactly
one answer can win, enforced under the request's row lock in the service (not the UI), and a
proposal changes status and moves the hold in one transaction; endpoints reject an expired request
themselves and the sweep only persists it; (B) *No thanks* is `PROPOSED` -> `DECLINED` and ends the
proposed hold at once (spec R31a, R43). The Playwright journey runs the real front desk -> patient
flow. Covers FR-BKG-04, 05, 06, 07 (the
no-show counter), 08, FR-PRT-06 (a) and FR-UX-03 (what waits for the desk). Rules:
`docs/specs/booking-requests.md` section 13, R31-R52 (Draft). Patient notifications (push, email,
in-app for patients) stay in P6; P5 shows every outcome in the portal and sends the existing
WhatsApp booking confirmation when the record has consent.

Facts the design rests on (checked in the code):

- A request is `PENDING` only (CHECK in `0029`); its hold is counted by `resolve_holds`, which
  today would block the request's **own** accept.
- Registering a patient needs name, phone and sex, and exactly one of date of birth or **age**
  (`Age.from_recorded_age` exists); the phone check returns up to 10 candidates
  (`PAT_PHONE_EXISTS`). Search is `GET /patients?q=`.
- Linking (`_create_link`) locks the record and enforces one active link per record and per
  account per clinic (`PRT_ALREADY_LINKED`); `LinkMethod` has `INVITE` and `RX_LINK`, and the
  `0025` CHECK allows only those.
- The worker runs recurring jobs every minute through `RECURRING` (no-show sweep every 5 minutes
  is the pattern); a new job kind is a migration.
- There is no per-patient no-show count anywhere yet, and nothing notifies a portal account.
- `APPOINTMENTS_MANAGE` and `PATIENTS_MANAGE` are held by every role.

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| 1 | States | `PENDING` -> `ACCEPTED` \| `DECLINED` \| `PROPOSED` \| `EXPIRED`; `PROPOSED` -> `ACCEPTED` (the patient takes it) \| `DECLINED` (the patient says no) \| `EXPIRED`. Every change only from an open state, under the request's row lock; a second answer is 409 **`BKG_ALREADY_ANSWERED`** ("Someone has already answered this request") | B: separate tables per outcome (more joins, no gain) |
| 2 | Accept (FR-BKG-05, FR-PRT-06 a) | One staff action in one transaction: lock the session and the request; the request's own hold is excluded (`resolve_holds(..., exclude=request.id)`), other patients' holds still count; book with source **`PUBLIC_PAGE`** (the existing confirmation and staff notification follow); **link** the account to the record (method **`BOOKING`**, actor STAFF); mark `ACCEPTED` with `patient_id`, `appointment_id`, `decided_by`, `decided_at`; audit `booking_request.accepted` (IDs only). If the time was taken after the hold lapsed: 409 `APT_SLOT_TAKEN` / `APT_SESSION_FULL`, and the desk proposes instead | B: accept without linking (the patient would not see the appointment; FR-PRT-06 a says link) |
| 3 | Matching the record | The accept form opens with **candidates by the request's phone** (name, code, age, and the no-show count) and a search box. Choose one, or **Create new** prefilled with the account's name, the phone, the age (recorded as age, `age_is_estimated`) and sex (staff must choose sex if the patient did not give it). If the account is **already linked** in this clinic, that record is the only choice. A record linked to another account is refused `PRT_ALREADY_LINKED`. Never automatic by phone alone | B: auto-match on phone and name (family members share phones, FR-PAT-02) |
| 4 | Decline (FR-BKG-04, 05) | A reason from a short list the patient sees in their language: *Time no longer available*, *Doctor unavailable*, *Please call the clinic*, *Not something we can book online*, *Duplicate request*, *Other*; plus an optional staff note (200 characters, **staff only**, never shown to the patient, so nothing clinical leaks). Ends the hold at once. Audit `booking_request.declined` with the reason code | B: free-text reason shown to the patient (staff may write clinical text into it) |
| 5 | Propose another time (FR-BKG-04) | Staff choose another session or slot of the **same doctor** (the booking drawer's picker, holds respected) **and match the record now** (as in point 3). The request becomes `PROPOSED`: its hold **moves** to the new time (`session_id`/`slot_start` replaced, the original kept in `original_session_id`/`original_slot_start`), with a fresh hold of the clinic's hold time, never past 1 hour before the new time. The patient sees *The clinic suggests Tue 11:00* with **Accept this time** / **No thanks**. Accept by the patient books, links and marks `ACCEPTED` exactly as point 2 (actor PATIENT; staff already agreed); *No thanks* is `DECLINED` by the patient. A proposal unanswered when its hold ends `EXPIRED`. One proposal per request | B: decline with a suggested time in text; the patient asks again and the desk answers twice (slower, and the time is not kept). C: propose any doctor (a different doctor is a different request) |
| 6 | Expiry (FR-BKG-06) | Read as expired at once wherever it matters (`PENDING` with `respond_by <= now`, `PROPOSED` with `hold_expires_at <= now`): not answerable, not held, shown as Expired. A **sweep every 5 minutes** (new job kinds, the no-show pattern) writes `EXPIRED` and audits `booking_request.expired` (SYSTEM), so counts and P6's notice have a row to act on. The 4-hour window stays a constant (P4 decision); a clinic setting can come when a pilot asks | B: a job only (expiry late by up to 5 minutes). C: read-time only (nothing for P6 to notify on) |
| 7 | The inbox (FR-UX-03) | *Booking requests* becomes the inbox: **Open** (oldest first, with "reply by 14:30" and *Held* / *Hold ended*), **Answered** (last 7 days: outcome, by whom, when) and an **Expired** count. Row actions *Accept*, *Propose another time*, *Decline*. The nav item shows the open count; Today (clinic scope) gets a **Requests waiting** tile next to *Bookings to move*. Doctors use the same inbox (FR-BKG-04 lets them), as for booking | B: actions in the notification only (no overview) |
| 8 | Response rate and the no-show counter (FR-BKG-06, 07, PRD risk) | Owners' Today shows **Answered in time, last 30 days** (answered before `respond_by` / all requests decided or expired) and the expired count. The no-show counter is per **record** (NO_SHOW appointments in the last 12 months), shown on the accept form's candidates and on accepted rows; there is no automatic ban (FR-BKG-07) | B: a counter per account (an account's history at other clinics is not this clinic's business) |
| 9 | The patient's side (R23) | *My appointments* lists open and recently answered requests (7 days): *Requested*, *Suggested another time* (with the two buttons), *Declined - <reason>* with a call button, *Expired - the clinic did not reply in time* with the call button. An accepted request disappears from the list because the appointment now appears under its clinic (the account is linked). English and Hindi. No new channel until P6 | B: keep answered requests forever (clutter; the appointment is the record) |
| 10 | Storage and contract | Migration `0030`: request statuses widened; columns `patient_id`, `appointment_id`, `decided_at`, `decided_by` (user, null for patient or system), `decided_by_type` (STAFF \| PATIENT \| SYSTEM), `decline_reason`, `decline_note`, `original_session_id`, `original_slot_start`; the open-request unique index becomes `WHERE status IN ('PENDING','PROPOSED')`; live holds count both open states; `LinkMethod.BOOKING` and its CHECK; two job kinds. Contract 0.34.0: `POST /booking-requests/{id}/accept`, `/decline`, `/propose`; `GET /booking-requests?state=open\|answered`; `GET /booking-requests/{id}/candidates`; `POST /portal/booking-requests/{id}/accept-proposal` and `/decline-proposal`; request items gain `status` and outcome fields | B: put the proposal in its own table (a second hold source to count everywhere) |

Testing for P5 (per the developer's rule of 26 Oct 2026): unit and integration tests for the new
code, the booking-request contract test, the affected web tests, lint and typecheck, and one
Playwright journey (accept with a new record; propose and the patient accepts; decline). The full
suites run once at the end of M6b.

### As built (M6b-P5)

Built 26 Oct 2026 to the approved design and its two clarifications. Details settled in the build:

- **Storage.** Migration `0030` widens the status CHECK and adds `patient_id`, `appointment_id`,
  `answered_at`/`answered_by` (the staff member's first answer: accept, decline or propose),
  `decided_at`/`decided_by_type` (when and how it became final), `decline_reason`,
  `decline_note`, `original_session_id`/`original_slot_start`, with CHECKs that tie them to the
  status. The one-open-request index now covers `PENDING` and `PROPOSED` (its name is kept).
  `LinkMethod.BOOKING` and the `schedule_request_expiry` system job kind join their CHECKs.
- **One answer wins (R31a).** Every answer reads the request, locks the sessions it touches, then
  the request row, and checks again (open, same status, same session, before the deadline); the
  loser is 409 `BKG_ALREADY_ANSWERED`. Proven by a parallel-accept test (one 201, one 409, one
  appointment). A proposal moves the hold and changes the status in the same transaction.
- **Accept** books through the same steps as a staff booking (`resolve_holds(exclude=...)` drops
  only this request's hold), source `PUBLIC_PAGE`, then `link_for_booking` (actor STAFF, or
  PATIENT when the patient takes a proposal), then `booking_request.accepted`. A new record goes
  through `add_patient_record`, now shared with registration. Staff accept only `PENDING`; a
  proposal waits for the patient.
- **Propose.** A proposal's deadline (`respond_by`) becomes its hold's end, so "expired" means the
  same check for both open states. The record is chosen when proposing; a new one is created then.
- **Expiry.** Endpoints read an open request past `respond_by` as expired; a 5-minute sweep
  (`schedule_request_expiry` -> `expire_booking_requests` per clinic) writes `EXPIRED` with a
  SYSTEM audit row.
- **Counts.** `GET /booking-requests` returns `open_count` and `expired_7d`; Today has
  `booking_requests_open` (clinic scope) and, for owners, `requests_answered_30d` and
  `requests_expired_30d` (the rate is answered / (answered + expired)). The nav shows the open
  count beside *Booking requests*, read as "N waiting"; it is refreshed when the page changes.
- **No-show count** per record over 12 months (`appointments.count_no_shows`), on the accept and
  propose candidates only.
- **Web.** The inbox has Open / Answered, *Accept* and *Propose another time* drawers sharing one
  record picker (phone candidates, search, *Create new record* prefilled), and *Decline* with the
  reason and a staff-only note. The patient's *My appointments* shows the four states with *Accept
  this time* / *No thanks* and the call button.
- **Tests (changed code only, per the 26 Oct rule).** API: domain and integration
  (`test_booking_answers_http.py`, 14), contract, tenancy (cross-clinic and cross-account cases
  for the six new ID routes), migrations, worker wiring; web: the inbox, proposal and nav tests,
  the full web suite (629); Playwright `booking-answers.spec.ts` (the front desk -> patient flow),
  `booking-requests.spec.ts` and `workspaces.spec.ts`. The full API and Playwright suites run at
  the end of M6b.

Differences from the design (all small): the staff-only note is shown on the *Answered* list;
staff may decline a pending proposal (it withdraws the offer); the patient's confirmation after
*Accept this time* is the appointment appearing under the clinic (the list reloads).

---

## M6b-P6 - Patient notifications and the live token link

Proposed 26 Oct 2026, **awaiting the developer's approval**. The last phase of M6b. Covers
FR-NTF-01 and FR-NTF-04/05 for patients, FR-REM-03 (medicine reminders, in the app) and
FR-QUE-06. Rules: `docs/specs/patient-portal.md` section 13, R55-R74 (Draft); the live link's
security choice is ADR-0019 (Proposed). Testing follows the 26 Oct rule (changed code only); the
**full API and Playwright suites run once at the end of this phase, closing M6b**.

Facts the design rests on (checked in the code):

- The notification service (ADR-0017) writes **staff** in-app rows only (`notifications`,
  recipient a user); titles are English strings built from typed values. Nothing addresses a
  patient account.
- Patients today get **WhatsApp** only, to the clinic record's phone and only with that record's
  consent: booking confirmation, appointment reminders, cancellation notice, prescription link,
  follow-up reminder. New WhatsApp templates need Meta approval (L-02, still pending).
- P5's decline, propose and expiry write audit rows only; accept publishes `AppointmentBooked`.
- `medicine_reminder_prefs` is stored ("P6 delivers"), with the account's slot times.
- Reminder rows (appointment, follow-up) exist only for records with WhatsApp consent.
- There is no web push, service worker or manifest; the portal polls nothing yet.
- Signed public links (`domain/links/token.py`) have a purpose map holding only `RX_VIEW`.
- The queue orders a session by token (or slot); no "position" is computed anywhere.

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| 1 | Where patient notifications live | A new table **`patient_notifications`**: clinic, **account**, kind, `event_key` (unique per account), the entity and its link, `params` (IDs and a time only), `created_at`, `read_at`. The **title is rendered at read time** in the account's language (English or Hindi) from the kind and params, so a language switch changes past notices too and no text is stored. Read through a reviewed cross-clinic lookup by account, filtered by the portal scope (an unlinked or suspended clinic's notices disappear, as its records do). Kept 90 days, like staff notifications | B: reuse `notifications` with a nullable account recipient (mixes staff and patient rules; titles are stored English). C: store rendered text in both languages (duplication; no gain) |
| 2 | Who receives them | The **account** a request belongs to (booking events), or the account **linked** to the appointment's or prescription's record in that clinic. A record with no linked account gets nothing in the app (WhatsApp is unchanged). Never by phone | B: every account whose email or phone matches (FR-PRT-06: never by phone alone) |
| 3 | The patient event catalogue | **Booking:** accepted, declined (with the reason's words), another time suggested, expired. **Appointment:** confirmed (a staff booking, not one from an accepted request: that notice already says booked), moved, cancelled. **Prescription ready** (issued or revised: "New prescription from Dr X", no medicine). **Medicine due** (point 5). New events `BookingRequestAnswered(request_id)` and `BookingRequestExpired(request_id)` are published by P5's answers and the expiry job; the existing appointment and prescription events gain a patient recipient in the same service | B: also appointment-reminder and follow-up-due notices in the app now (those rows exist only for WhatsApp-consenting records; making them channel-independent is a reminders change: proposed for M7, see open question 3) |
| 4 | Channels and preferences | **In the app:** every kind, on by default, each switchable under *Account -> Notifications*; in-app ignores quiet hours (FR-NTF-05). **Email (new, recommended):** only the four **booking outcomes**, to the account's **verified** email, English or Hindi, on by default and switchable; a link to the portal, no reason or note in the email. **WhatsApp:** unchanged (the clinic record's consent and approved templates). Preferences in `patient_notification_preferences` (account, kind, channel) | B: in-app only (a patient who asked for a time may not open the app for hours, so an answer or a proposal is missed). C: new WhatsApp templates (blocked on L-02 approval) |
| 5 | Medicine due (FR-REM-03) | From the stored reminder choices: for each enabled line and slot of a **current** prescription inside its course, at the account's time (or the chosen `remind_at`), one in-app notice per account, slot and day: "Morning medicines · 08:00" -> `/portal/medicines` (never a medicine name, dose or count). A **sweep every 5 minutes** (the expiry pattern) creates those due since the last run, at most 30 minutes late; a missed day is not back-filled. In-app only. The portal shows a line under the plan that these appear when the app is open (no push yet) | B: phone push notifications now (needs a service worker, VAPID keys and a permission flow: a phase of its own). C: WhatsApp medicine reminders (template approval; FR-MSG-04 forbids medicine names anyway) |
| 6 | The notification centre (FR-NTF-05) | A **bell** in the portal header with the unread count, polling a summary every 30 seconds with ETag only while the tab is visible (the staff bell's pattern); `/portal/notifications` lists the newest 50 with read state, *Mark all as read*, and each opens its item (the appointment's clinic group, the request, the prescription, the medicine plan). 360 px, English and Hindi, under 200 KB | B: a list only, no bell (FR-NTF-05 asks for a badge) |
| 7 | The live token link (FR-QUE-06) | A **signed link per appointment**, `PUBLIC_BASE_URL/q/{token}` (purpose `QUEUE_VIEW`, valid from the session's day until 2 hours after it ends). The page, **without sign-in**, shows the clinic, the doctor, the patient's **token or slot time** and "**3 ahead of you**", "**Now seeing token 4**", or "It's your turn" / "Your visit is done" / "This appointment was cancelled"; **no name, phone or reason**. It refreshes every 20 seconds (ETag) and shows when it last updated. Rate limited like the prescription link. Patients reach it from *My appointments* (today's appointments) and staff can copy it from the queue row to send by hand. ADR-0019 explains why it needs no last-4 check | B: the last-4 check first (one more step for "am I next?", for no clinical data). C: only inside the signed-in portal (unlinked walk-ins could not use it) |
| 8 | Position and words (FR-QUE-06) | Computed from the session's active appointments on each read: **ahead** = BOOKED or ARRIVED entries before this one in queue order (token, else slot), **now seeing** = the IN_CONSULTATION entry's token or slot; nothing about anyone else. Slot mode says "Your time 10:30 · 2 ahead of you" | B: an estimated wait in minutes (needs consultation-length data; misleading early) |
| 9 | Privacy and safety | Titles, emails and the live page carry no diagnosis, medicine, reason, note, phone or age (FR-MSG-04, FR-NTF-06); logs carry IDs and counts. Notices are the account's alone (a cross-account tenancy case for every new ID route). Unlinking a clinic hides its notices and voids its live links for that account's view | — |
| 10 | Storage and contract | Migration `0031`: `patient_notifications`, `patient_notification_preferences`, the link purpose and the medicine sweep job kinds. Contract 0.35.0: `GET /portal/notifications`, `GET /portal/notifications/summary` (ETag), `POST /portal/notifications/{id}/read`, `POST /portal/notifications/read-all`, `GET`/`PUT /portal/notification-preferences`, `GET /portal/appointments/{id}/live-link`, staff `GET /appointments/{id}/live-link`, public `GET /public/queue/{token}` | — |

Testing for P6: unit and integration tests for the new code (recipients, rendering in both
languages, idempotency, the medicine sweep's window, position words, the link's expiry), the
contract and tenancy cases, the affected web tests, and two Playwright journeys at 360 px (a
patient's bell after the desk accepts and proposes; the live link moving as the queue moves).
Then the **full** API and Playwright suites, closing the milestone.

Open questions for the developer:

1. **Email for booking outcomes** (point 4): add it now (recommended), or in-app only?
2. **The live link without a last-4 check** (point 7, ADR-0019): acceptable, given it shows only
   a token number and a queue position?
3. **Appointment-reminder and follow-up-due notices in the app** (point 3): leave for M7 as
   proposed, or bring them into P6 (the reminders change makes the phase noticeably bigger)?
