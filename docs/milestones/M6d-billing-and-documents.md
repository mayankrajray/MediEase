# M6d — Billing and documents: design notes

| Field | Value |
|---|---|
| Status | Proposed 26 Oct 2026, after M6c merged (PR #54); **approved by the developer 26 Oct 2026**: the phase plan, milestone decisions B1–B9, D1–D9 and the P1 design, all on the recommendations |
| PRD | v1.2 §0 (C12, C14), §8.1 (permission matrix), §8.5 (FR-VIS-04), §8.14 (FR-BIL-01..07, FR-SUB-01), §12 (plans) |
| Specs | `docs/specs/billing.md` (P1–P5, written at P1 and grown per phase); `docs/specs/visit-attachments.md` (P6); `docs/specs/plans-and-trial.md` (P7) |
| ADR | ADR-0022 (proposed with P2): bills are immutable documents with their own numbering, corrected only by credit notes |
| Covers | FR-BIL-01..07, FR-VIS-04, FR-SUB-01 |
| Issue / branch / PR | #63 · `m6d/63-billing-and-documents` (from `main` at `ec721e6`, after PR #54 merged) · one PR for the milestone (ADR-0011) |
| Exit criterion (PRD §13) | The daily collection matches recorded payments (a reconciliation test over bills, payments and credit notes); plan limits are enforced on every path that adds a doctor or a user; `make e2e` green |
| Out of scope | Payment gateways, UPI collect and automated subscription billing (PRD §12: manual in MVP); insurance and TPA (§6.3); GST invoicing (D3); the subscription lifecycle after the trial: overdue, grace, read-only, suspension, data export (FR-SUB-02, 03; PRD M10+); MediEase's own invoice to clinics and WhatsApp usage billing (M8); inventory (FR-INV) |

## Facts the design rests on (checked in the code, 26 Oct 2026)

- **No billing exists.** No table, permission, audit category or screen. Money elsewhere: the
  public profile fee `doctors.fee_paise` (M6c-P5, 0–1,000,000) and message costs in millipaise
  (M5). The web formats paise with `formatPaise` and `rupees` (`lib/format/money.ts`).
- **Permissions** (`domain/identity/permissions.py`): 14 permissions; front desk holds only the
  every-role set, and a matrix test and a route-policy test cover every one. PRD §8.1 already
  states the billing rows: *create billing entries and receipts* for owner, doctor (own
  consultations) and front desk; *edit fee schedule* for the owner only.
- **Visits** always come from an appointment (`Visit.start` needs `IN_CONSULTATION`); walk-ins
  are ordinary appointments (`AddWalkIn`). A visit locks 24 hours after completion; later changes
  are addenda.
- **PDFs** (`application/prescriptions/pdf.py`): render once on first download, store write-once
  under a key, serve through an audited route; WeasyPrint with vendored fonts and a fetcher that
  refuses everything else. `PdfRendererPort.render(RxDocument)` is typed to prescriptions.
- **Patient links** (`domain/links`): HMAC-signed tokens with a last-4 challenge and a lockout;
  one purpose (`RX_VIEW`) and a `prescription_id` column, so a receipt link needs a purpose code
  and a general resource column.
- **Storage** is private and write-once (`put`, `get`, `exists`, `delete`), never a public URL.
  The certificate sniffer (`domain/onboarding/certificate.py`) recognises PDF, JPEG and PNG by
  their first bytes, but is tied to onboarding (5 MB, "doctor N").
- **Numbering:** patient codes are allocated under the clinic row lock
  (`Clinic.allocate_patient_code`), with no gaps on rollback; application references use a
  sequence per year.
- **Staff and doctors** are created in `InviteStaff.in_transaction`, `AddDoctor.in_transaction`
  (also used by approval) and reactivated by a new invitation; `AcceptInvite` activates a member.
  These are the choke points for plan limits. **No plan, subscription or trial concept exists.**
- **Migrations** end at `0035`; the contract is 0.42.0.

## Phase plan

| Phase | Builds | Requirements |
|---|---|---|
| P1 | **Fee schedule.** The clinic's services (consultation, follow-up, procedure, other) with a default price, per-doctor prices, the owner's *Fees* page; the public profile fee read from it (D8) | FR-BIL-01 |
| P2 | **Bills.** A draft bill from a completed visit (the doctor's consultation or follow-up prefilled) or for a patient without a visit; line items, a discount per line or on the bill (amount or %), notes; *Issue* makes it immutable with a clinic number; corrections by credit note (cancel all or some lines); every change audited | FR-BIL-02, 07 |
| P3 | **Payments and dues.** Record cash, UPI or card payments (partial allowed, never more than the balance), a refund against a credit note, the balance on each bill, a patient's dues on their profile and the queue, the clinic's dues list | FR-BIL-03, 05 |
| P4 | **Receipts.** The bill and each payment as a PDF on the clinic's letterhead (rendered once, A5/A4); a patient link with the last-4 check (*Receipt* purpose), shown with a QR at the desk, and the bills in the patient portal | FR-BIL-04 |
| P5 | **Daily collection.** One clinic-local day: totals by mode and by doctor, refunds, the net, the list behind it; CSV export (cell-injection safe, audited); the reconciliation test of the exit criterion | FR-BIL-06 |
| P6 | **Report attachments.** PDF, JPEG or PNG up to 10 MB on a visit, checked by their first bytes, private, audited on every open; the doctor may share one with the patient's portal | FR-VIS-04 |
| P7 | **Plans, trial and limits.** A plan on each clinic (Solo, Clinic, Clinic Plus) with doctor and user limits enforced at every path that adds or reactivates one; a 14-day trial with no card; the ops console sets the plan; the owner sees the plan, the usage and the days left | FR-SUB-01 |

Testing follows the M6c rule: per phase, the changed code's tests plus lint and typecheck; the
full API and Playwright suites once, at the end of P7.

## Milestone decisions (approved)

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| B1 | Money | **Integer paise everywhere** (AGENTS.md); one `Money` value object in the domain with addition, a percentage rounded half up to the paisa, and no negatives except on a credit note's totals. Limits: a line up to ₹1,00,000, a bill up to ₹10,00,000 | Decimal rupees (the project rule is paise) |
| B2 | Permissions (PRD §8.1) | New **`BILLING_MANAGE`** (all three roles: draft, issue, record payments, credit notes, receipts), **`FEES_MANAGE`** (owner) and **`COLLECTION_VIEW`** (owner and front desk: daily collection, dues list). A doctor's bills are limited to their own visits in the use case, as §8.1 says. Front desk sees bills, never clinical content: a line shows the service name the owner defined | Reuse `CLINIC_MANAGE` for fees (it also edits clinic settings the front desk must not touch) |
| B3 | What a bill holds | A **snapshot**: each line copies the service name, the doctor and the unit price at drafting, so a later fee change never alters a bill. No diagnosis, medicine or note from the visit is ever copied | Reference the fee schedule live (an issued bill would change) |
| B4 | Immutability (FR-BIL-07, ADR-0022) | `DRAFT → ISSUED`; a draft may be edited or discarded; an issued bill never changes. A **credit note** (its own number) reverses all or some lines; a fully credited bill shows `CANCELLED`. A bill's balance = total − credit notes − payments + refunds | Editable bills with a history table (FR-BIL-07 says immutable) |
| B5 | Numbering (D1) | Per clinic and **financial year** (April–March), from the clinic's patient-code prefix: `SC/26-27/0001` for bills, `SC/CN/26-27/0001` for credit notes. Allocated only at *Issue*, under the clinic row lock, so drafts take no number and there are no gaps | One continuous series per clinic |
| B6 | Payments | A payment is recorded against one issued bill (mode, amount, an optional reference up to 40 characters for UPI or card, who took it, when). Never more than the balance. A wrong payment is **voided** the same clinic day with a reason (audited); after that only a credit note and refund correct it. No advance or deposit balance | Allow payment across bills (allocation rules for a small gain) |
| B7 | Documents | Bill and payment receipts are PDFs on the prescription pipeline (render once, write-once storage, audited download), with a second document type for the renderer. The patient link gains a purpose and a general resource column (`resource_id`), keeping RX links unchanged | A separate receipt pipeline (two letterheads drift) |
| B8 | Attachments (D7) | Clinical content: viewing needs `CLINICAL_VIEW`, adding needs `CLINICAL_WRITE`, and **front desk may upload without viewing** (scanned reports at the counter) when D7 says so. 10 MB, PDF/JPEG/PNG by first bytes (the sniffer moves to `domain/shared/files.py`), served `inline` with `nosniff` and a sandbox CSP. Deleted only within 24 hours of upload by its uploader; after that they stay, like addenda | Any role sees attachments (§8.1 forbids clinical content to front desk) |
| B9 | Plans (D4, D5) | `clinic_subscriptions` (platform data, one row per clinic): plan, trial start and end, limits taken from the plan (Solo 1 doctor and 2 users counting the owner; Clinic 3 and 5; Clinic Plus 5 and unlimited). Enforced in one domain check called by `InviteStaff`, `AcceptInvite`, `AddDoctor`, doctor reactivation and approval; refused with `SUB_LIMIT_REACHED` (409) naming the limit. Existing clinics get *Clinic Plus* in the migration so nothing breaks | Limits only in the web (the API is the control) |

## The developer's decisions (26 Oct 2026)

Locked when M6d was approved, each on the recommendation; they override anything below that reads
otherwise.

| # | Question | Decision |
|---|---|---|
| D1 | Bill numbering: per financial year (`SC/26-27/0001`) or one continuous series? | Per financial year, as Indian clinics and accountants expect |
| D2 | May a doctor record payments, or only create and issue their own bills? | Doctors may record payments on their own bills (§8.1 "billing entries and receipts") |
| D3 | Tax: bills carry **no GST** fields in M6d (most clinical services are exempt), and the receipt says nothing about tax. Confirm, with counsel later if a clinic needs GST | No tax fields; a note in the RUNBOOK and an open item for counsel |
| D4 | Solo's "1 doctor + 1 staff user": does the owner count as one of the users? | The owner counts: Solo = 2 users, 1 doctor (an owner who practises is the doctor) |
| D5 | When does the 14-day trial start, and what happens when it ends in M6d? | Starts when the clinic becomes `ACTIVE`. At the end, M6d shows an owner banner and an ops flag only; nothing is locked (the lifecycle is FR-SUB-02, later) |
| D6 | Receipt delivery: link and QR at the desk now, WhatsApp when a receipt template is approved by Meta (L-02)? | Yes; the WhatsApp send is built behind the messaging port and stays off until the template exists |
| D7 | May the front desk upload a report to a visit without being able to open it? | Yes (counter scanning is common); viewing stays clinical |
| D8 | Should the public profile fee (M6c-P5) come from the fee schedule's consultation price? | Yes: one source; the owner's *Show fee publicly* switch decides whether it appears |
| D9 | Issue and branch: open the M6d issue and branch from `main` now, and commit this design there? | Yes |

## M6d-P1 — Fee schedule

Proposed and **approved 26 Oct 2026**.


Covers FR-BIL-01 and D8. Rules go into `docs/specs/billing.md` R1–R12.

| # | Decision | Recommended | Alternatives |
|---|---|---|---|
| 1 | What is stored | Migration `0036`: **`clinic_services`** (tenant: name up to 80, kind `CONSULTATION` \| `FOLLOW_UP` \| `PROCEDURE` \| `OTHER`, default price in paise, active, position) and **`doctor_service_prices`** (tenant: service, doctor, price; unique per pair). A doctor's price for a service is their own, else the default | Prices on doctors only (no procedures) |
| 2 | Starting point | Each clinic gets *Consultation* and *Follow-up* (inactive, no price) in the migration and at clinic creation, so the first bill always has something to offer | An empty schedule (the first bill would need set-up first) |
| 3 | Changes | Prices change from now on only (B3: bills snapshot). A service is retired, never deleted, once any bill uses it; names are unique among active services | Deleting services (breaks the history reading) |
| 4 | Who | `FEES_MANAGE` (owner) edits; `BILLING_MANAGE` (every role) reads the active schedule for drafting | Front desk edits prices |
| 5 | The public fee (D8) | The public `fee_paise` becomes the doctor's consultation price, shown only when the owner turns on *Show fee publicly* (per doctor, on *Directory*). Migration copies today's `fee_paise` into a doctor price for *Consultation* | Keep two fees (a public one and a billing one that disagree) |
| 6 | Screens | Owner: *Settings → Fees*: the services with their default price, a doctor-by-service table of overrides, add, rename, retire, reorder; amounts typed in rupees, stored in paise | One form per doctor |
| 7 | API | `GET /api/v1/clinic/fees` (`BILLING_MANAGE`), `POST /clinic/fees/services`, `PATCH /clinic/fees/services/{id}`, `PUT /clinic/fees/services/{id}/doctors/{doctor_id}` (`FEES_MANAGE`); contract 0.43.0; audit `fees.service_added`, `fees.service_changed`, `fees.doctor_price_set` (IDs and amounts only) | — |

Planned verification: domain tests (prices, kinds, names, retirement), integration (the default
pair at creation and in the migration, overrides, the public fee following the consultation
price, the permission matrix and a cross-clinic case), the migration test, contract, web
(*Fees* page). Failure path: a price above ₹1,00,000 or a duplicate active name is 422 naming
the field.

Open questions for P1: none beyond D8.

### P1 as built (26 Oct 2026)

Built as approved, with these refinements (rules in `docs/specs/billing.md` R1–R12):

- The starting *Consultation* and *Follow-up* are **active** (without a price), not inactive, so
  the schedule is usable at once and the public fee (D8) has its consultation service.
- A duplicate active name is **409 `BIL_SERVICE_NAME_TAKEN`** (a rule conflict, like the other
  `CLN_` conflicts), not 422; a price out of range stays 422. A clinic has at most 100 services
  (`BIL_TOO_MANY_SERVICES`).
- The public fee is the price for the first active `CONSULTATION` service in position order.
  `doctors.show_fee` (default false) is the *Show the consultation fee publicly* switch on
  *Directory*; the profile `PUT` takes `languages?` and `show_fee?` and refuses `fee_paise`.
- `doctors.fee_paise` is kept (expand-only) and deprecated; 0036 copies it into the doctor's own
  *Consultation* price and sets `show_fee` where it was set.
- Retiring is allowed whether or not a bill uses the service (there are no bills before P2);
  deletion does not exist.
- Web: `/settings/fees` in the owner's menu (*Fees*): a read-only price table for every billing
  role, and for owners a card per service, *Add a service* and *Restore*. Rupees are parsed with
  at most two decimals (`lib/format/money.ts` `parseRupees`).

Verified: changed-code API tests (1452 passed, including the repository and HTTP cross-clinic
cases, the permission matrix, the migration test and the contract), web tests for the touched
areas (73), ruff, mypy, import-linter, tsc, ESLint, `make contract-check`, `make up` to `0036`,
`make smoke`, and the workspaces and discovery journeys.

## M6d-P2 — Bills and credit notes

Designed and **approved in advance** by the developer (26 Oct 2026: "approving all the design choices
for P2-P7"). Rules: `docs/specs/billing.md` R13–R30. Decision record: ADR-0022.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | Storage | Migration `0037`: **`bills`** holds both bills and credit notes (`kind`), with the stored totals and `credited_paise`, `paid_paise`, `refunded_paise` (the last two used from P3). **`bill_lines`** holds each line's snapshot and final amount, tied by a CHECK. A credit note's line names the bill line it reverses (unique) | Separate credit-note tables (two copies of the line shape) |
| 2 | Bill discount | Shared across the lines in proportion by largest remainder, so each line's final amount is exact and a partial credit note refunds exactly what that line cost | Credit notes at the line's pre-discount value (would not add up to the total) |
| 3 | Numbering | `max(seq) + 1` per clinic, kind and financial year under the clinic row lock, with a unique index as the last guard | A sequence per series (gaps on rollback) |
| 4 | One bill per visit | A partial unique index on `visit_id` for open bills, and `BIL_VISIT_BILLED` carries the open bill's ID, so the queue's *Bill this visit* opens it | Several bills per visit (double billing at the desk) |
| 5 | Doctors | `BILLING_MANAGE` for every role (B2). A `DOCTOR` role is limited to bills with their own profile: 404 for another doctor's, 403 `BIL_NOT_YOURS` for drafting or listing as another | A separate permission for the doctor's own bills |
| 6 | Prefill | A visit's draft starts with the first active consultation service at the doctor's price. Follow-up is chosen by hand | Guessing follow-up from the appointment (no reliable signal) |
| 7 | Screens | *Bills* list (owner, front desk; *My bills* for doctors); the bill page (draft editor, issue, discard, credit notes); *Bill this visit* in the queue menu; *Bills* on the patient profile | A billing drawer in the queue (too much for a phone) |
| 8 | API | `GET/POST /api/v1/clinic/bills`, `GET/PUT/DELETE /bills/{id}`, `POST /bills/{id}/issue`, `POST /bills/{id}/credit-notes`; contract 0.44.0 | — |

### P2 as built (26 Oct 2026)

Built as designed. Verified: domain tests (pricing, the shared discount, limits, financial years,
the state machine, credit notes), HTTP tests (AC4–AC8, the doctor's scope, paging, two issues at
once), repository and HTTP cross-clinic cases, the migration test, route policies and the contract
(`tests/contract/test_billing_contract.py` also covers P1's fee routes). Web: the bills list, the
bill page, the patient's bills and the queue action (tests for the editor, issue, credit notes and
the list). Lint, typecheck and import contracts are clean.

## M6d-P3 — Payments and dues

Designed and approved in advance (26 Oct 2026). Rules: `docs/specs/billing.md` R31–R42.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | Storage | Migration `0038`: **`payments`** (tenant) holds payments and refunds (`kind`), mode, amount, reference, who and when, the clinic-local day, and the void (time, author, reason, all or none). The bill's `paid_paise` and `refunded_paise` (0037) are updated in the same transaction under the bill row lock | Summing payments on every read (slow dues lists) |
| 2 | Limits | A payment up to the balance; a refund only when overpaid, up to the amount owed back (B6) | Advances held on account (out of scope) |
| 3 | Corrections | A void on the same clinic-local day with a reason, never under a standing refund; after that a credit note and a refund. So a day's collection never changes once the day is over (P5) | Edits or deletes (no trail) |
| 4 | Permission | New **`COLLECTION_VIEW`** (owner, front desk) for *Dues* now and the daily collection in P5 (B2). Payments need `BILLING_MANAGE`, and doctors take them on their own bills (D2) | Dues for every role (doctors would see every patient's money) |
| 5 | Dues | `GET /api/v1/clinic/dues` (largest first, 200 at most, `patient_id` filter). The queue entry gains `dues_paise`, the patient profile shows it, and queue rows say "Dues ₹…" | A dues column on the patient table (one more migration and its upkeep) |
| 6 | Screens | *Payments* on the bill page (mode, amount at the balance, a reference for UPI or card, refund when overpaid, *Void* today only); *Dues* page | — |

### P3 as built (26 Oct 2026)

Built as designed. Verified: domain tests (limits, refunds, voids, the refund guard), HTTP tests
(AC9–AC12, two payments at once, a doctor's own bills, a void on an earlier day), repository and
HTTP cross-clinic cases, the permission matrix, route policies, the migration and the contract
(payments, dues and the queue). Web: the payments panel, *Dues*, the queue and profile amounts.

## M6d-P4 — Receipts

Designed and approved in advance (26 Oct 2026). Rules: `docs/specs/billing.md` R43–R54.

| # | Decision | Chosen | Alternatives |
|---|---|---|---|
| 1 | One document | The bill as it stands (lines, credit notes, payments, balance) is the receipt. Every payment shows on it, so no separate per-payment slip is printed | A slip per payment (more files, and the same numbers twice) |
| 2 | Render once | The renderer gains `render_receipt` (the same WeasyPrint adapter, fonts and assets-only fetcher; `receipt.html.j2`, `receipt.css`, the shared page stylesheet). A state counter (credit notes + payments + voids) keys the stored file `receipt/<clinic>/<bill>/s<n>.pdf`, so no column is needed and old files never change. The bill row lock stops a double render | A column for the key (one more migration and its upkeep) |
| 3 | Receipt link | Migration `0039`: `patient_links.bill_id` and purpose `RECEIPT` (token purpose code 2), `prescription_id` nullable, a CHECK tying each purpose to its column, one active receipt link per bill. The last-4 check, counting, lockout, rate limits and view token are reused unchanged. The receipt page is `/r/<token>` with its own cookie; a server route fetches the PDF with `X-Link-View` | A second link table (two copies of the challenge rules) |
| 4 | Portal | `GET /api/v1/portal/bills` and `/bills/{id}/receipt.pdf` through `PortalScope`; a *Bills* card on *My prescriptions* (in both languages) | A new portal tab (the tab bar is full on a phone) |
| 5 | WhatsApp (D6) | Not sent in M6d: no approved receipt template exists (L-02). Sending it later is one template plus one job on the messaging port | Sending without an approved template (Meta refuses it) |
| 6 | API | Staff `GET /bills/{id}/receipt.pdf`, `GET /bills/{id}/link`, `POST /bills/{id}/link/reset`; public `/public/links/{token}/receipt` and `/receipt.pdf`; describe gains `purpose`; contract 0.46.0 | — |

### P4 as built (26 Oct 2026)

Built as designed. The receipt is English only at M6d (the receipt template's Hindi review comes
with L-07). Verified with the real renderer: domain tests (rupee grouping, the document, the state
key) and HTTP tests (AC13–AC15, lockout and reset, a doctor's scope, a receipt token refused on the
prescription route). Also: the portal cross-account case, HTTP cross-clinic cases, route policies,
the migration, the contract, and the existing prescription link, PDF and portal-linking suites,
unchanged and green. Web: the receipt panel (print, QR), the `/r/` page, its verify and PDF routes,
and the portal's *Bills*.
