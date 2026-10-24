# M6b — Patient identity, portal and booking requests: design notes

| Field | Value |
|---|---|
| Status | Opened 24 Oct 2026 after M6a merged (PR #50); plan and P1 design approved by the developer 24 Oct 2026 (A on all eight); P1 built and confirmed (draft PR #52); P2 approved (A on all eight) and built; P3 designed, awaiting approval |
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
| P2 | **Portal web.** The fresh dashboard with *Find a doctor*, My Appointments grouped by clinic, prescriptions (the patient page and PDF), reminders; link and unlink screens; English and Hindi; 360 px; the patient-page budget | FR-PRT-03, 04, 05, 07, NFR-02, NFR-10, NFR-11 | Below (proposed 24 Oct 2026) |
| P3 | **Medicine planner.** Daily dose times derived only from each issued line's frequency, timing and days; *today* and *this course* views; optional in-app reminders | FR-REM-03 | Below (proposed 24 Oct 2026) |
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

## M6b-P3 — Medicine planner

Proposed 24 Oct 2026, **awaiting the developer's approval.** Covers FR-REM-03 (both entries: the
reminder, "optional per prescription, daily at chosen times until the course ends", and the plan,
"daily times derived only from each prescribed line's frequency, timing and days, shown to the
patient and optionally reminded in the app"). Rules are in `docs/specs/patient-portal.md`
R28–R38 (Draft for P3). Delivering "medicine due" notices is P6's patient notification centre.

Facts the design rests on:

- **What a line holds.** `PrescriptionItem`: the medicine's name, form, strength and dose as the
  doctor wrote them; `frequency` from a closed vocabulary (`1-0-0`, `0-1-0`, `0-0-1`, `1-0-1`,
  `1-1-1`, `1-1-1-1`, `SOS`, `ONCE`, `CUSTOM` + `frequency_text`); `timing` (`BEFORE_FOOD`,
  `AFTER_FOOD`, `WITH_FOOD`, `EMPTY_STOMACH`, `BEDTIME`, `ANY`); `duration_days` (optional).
  Prescriptions are versioned; the current one is the chain's latest issued version.
- **The boundary** (AGENTS.md §7, FR-RX-10): MediEase never generates medical advice, drug
  suggestions or dosage logic. A plan may only *lay out* what the doctor wrote; it must never
  compute a dose, merge lines, move a dose relative to food, or fill a gap the doctor left.
- **The portal today.** P1's scope gives a linked record's current prescriptions; the patient
  page already words frequency and timing in English and Hindi
  (`domain/prescriptions/patient_view.py`). There are no patient notifications yet (P6), and
  WhatsApp templates still wait for Meta (L-02).

| # | Question | A (rec) | Rejected |
|---|---|---|---|
| 1 | How a line becomes times | A fixed table from the **frequency code only**: `1-0-0` morning; `0-1-0` afternoon; `0-0-1` night; `1-0-1` morning and night; `1-1-1` morning, afternoon, night; `1-1-1-1` morning, afternoon, evening, night. `SOS`, `ONCE` and `CUSTOM` get **no times**: they are listed as "As the doctor wrote" with the doctor's words (`frequency_text`). **Timing is shown in words** beside the dose ("after food"), never turned into an offset; `BEDTIME` puts a once-a-night line at the night slot, nothing more | B: derive clock offsets from timing ("30 minutes before breakfast"): dosage logic the doctor did not write. C: parse `frequency_text` ("every 6 hours"): free text, guessing |
| 2 | Which clock times the slots are | The patient's own **daily times**, one per slot, defaults morning 08:00, afternoon 14:00, evening 18:00, night 21:00, changed under *Account* (each 05:00–23:30, in order). Stored on the account (migration `0027`). Times are wall-clock times of the clinic's zone (all linked clinics are in India today); the plan says the zone | B: one fixed clock (a night-shift worker cannot use it). C: per prescription (four times to set for every visit) |
| 3 | Which days | A course starts on the **issue day of the current version** (clinic calendar) and lasts `duration_days` days, that day counted as day 1. A revision starts its own course from its issue day; the superseded version's plan disappears with it. A line **without** a duration is "Until the doctor says", shown every day without an end and with no day count. Courses that ended more than 7 days ago are not shown | B: start the day after issue (the doctor may have given the first dose in the clinic, but the prescription does not say so either way). C: hide lines without a duration (the patient still takes them) |
| 4 | Where the plan is computed | In the **API**: a pure function in `domain/prescriptions/plan.py` from the issued versions and the account's times, behind `GET /portal/medicine-plan?date=YYYY-MM-DD` (today by default, ±30 days). One rule, unit-tested, reused by P6's reminders; the web only lays it out | B: in the web (P6's server-side reminders would need a second copy). C: precomputed rows in a table (a revision or a time change would have to rewrite them) |
| 5 | What the patient sees | A fifth tab, **Medicines**: *Today* (by slot: Morning, Afternoon, Evening, Night, then "As the doctor wrote"; each entry: medicine, dose, timing in words, clinic, "day 3 of 5") and *This course* (per prescription: medicines, start and end, days left). A line appears **once per slot it was prescribed for**; two prescriptions with the same medicine are shown as two entries, never merged. Every screen carries "This plan only lays out your prescription. If anything is unclear, ask your doctor." | B: a calendar grid (heavy at 360 px, against the budget). C: merge identical medicines (a clinical judgement) |
| 6 | Marking doses taken | **Not in P3.** No adherence record is kept; the plan is a view | B: a "taken" tick per dose (new health data about the patient, with consent, retention and display questions the PRD does not answer yet; can follow in a later phase) |
| 7 | The optional reminder (FR-REM-03) | Per prescription, **Remind me** on *This course* (off by default), stored as a tenant row of the linked record (`medicine_reminder_choices`: clinic, patient, account, prescription chain, on/off), cleared when the link ends. P3 stores and shows the choice; **P6 delivers** it as an in-app "medicine due" notice at each slot time until the course ends, with no medicine name in the notice (FR-NTF-06). No WhatsApp | B: browser push now (a service worker and keys, new infrastructure, before the notification centre exists). C: WhatsApp (templates wait for L-02; message bodies may not name medicines, so it would add little) |
| 8 | Wording and languages | Slot names, "day 3 of 5", "Until the doctor says" and the safety line in English and Hindi (`lib/i18n/portal.ts`); **frequency and timing words come from the patient page's own vocabulary** in the API, so the plan and the prescription never word a line differently; medicine names and doses exactly as written | B: new words for the plan (two ways to say the same instruction) |

Fixed points:

- **API.** Migration `0027`: `patient_accounts` gains `morning_time`, `afternoon_time`,
  `evening_time`, `night_time` (`time`, with the defaults above and a CHECK that they increase);
  table `medicine_reminder_choices` (tenant data, scoped repository, unique per account and
  chain). `PATCH /portal/me` accepts the four times; `GET /portal/medicine-plan?date=`;
  `PUT /portal/prescriptions/{rx_id}/reminder {on}` (the current version of a linked chain, else
  404). Contract 0.31.0. Nothing here is audited (a patient's own view and preference); changes
  are logged with IDs only.
- **Code.** `domain/prescriptions/plan.py` (`plan_for_day`, `course_of`), use cases in
  `application/portal/records.py`, the *Medicines* tab and screens in `features/portal/`.
- **Unchanged:** prescriptions, the patient page, staff screens, every P1 and P2 rule.

Planned verification:

- **Unit:** every frequency code to its slots; `SOS`, `ONCE`, `CUSTOM` untimed with the doctor's
  words; a duration's first and last day on the clinic's calendar; no duration; a revision
  replacing its predecessor; two prescriptions of one medicine kept apart; the times' order.
- **API:** the plan for a linked record only (another clinic's or record's never appears), a
  date outside ±30 days is 422, the times' validation, the reminder choice (current version only,
  cleared on unlink), migration `0027` up and down, contract; the portal tenancy suite gains the
  new route with an ID.
- **Web:** *Today* and *This course* in both languages, the safety line, a line under each of its
  slots, untimed lines, the times form and the reminder switch.
- **Playwright (360 px):** after linking the PRD sample (Syrup X, `1-0-1`, 5 days), *Medicines*
  shows it under Morning and Night as "day 1 of 5", the course ends on day 5, changing the
  morning time moves it, *Remind me* stays on after reload; under 200 KB and axe-clean in both
  languages. Failure path: after unlinking, the plan is empty.
- **Gates:** `make lint typecheck contract-check test` and `make e2e`.
