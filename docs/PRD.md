# MediEase — Product Requirements Document

| Field | Value |
|---|---|
| Product | MediEase (working name) |
| Document owner | Product team (Sitare University Startup Program, Group 1) |
| Status | v1.1 — product rules changed by the developer on 20 Oct 2026 (§0) |
| Last updated | 20 October 2026 |
| Target segment | Independent clinics and small specialty hospitals, 1–4 doctors, India |
| Related documents | [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_MODEL.md](DATA_MODEL.md) · [API.md](API.md) · [../SPECS.md](../SPECS.md) · [../TASKS.md](../TASKS.md) · [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md) |

> **How to read this document.** Sections 1–5 explain *why* we are building MediEase and *for whom*.
> Sections 6–9 define *what* it must do, with stable requirement IDs (`FR-…`, `NFR-…`) that specs,
> tasks, tests and commits reference. Sections 10–14 cover *how we will know it works* and *how it
> ships*. Anything describing *how the code is built* lives in the architecture documents, not here.

---

## 0. Changes in v1.1 (20 October 2026)

Decided by the developer after M5. Where a later section still says otherwise, this section wins.

| # | Change | Replaces | Built in |
|---|---|---|---|
| C1 | **Patient portal.** Patients may sign in on the web (Google sign-in or email and password) to see their upcoming and past appointments, saved prescriptions, reminders, medicine plan and notifications. It is a mobile-first web app; nothing is installed. A sign-in is linked to a clinic's patient record only by proof the clinic gave the patient: a clinic invite or a prescription link (FR-PRT) | §6.3 "A patient mobile app" non-goal; principle 2 now reads "no patient *install*" | M6 |
| C2 | **Staff sign-in with Google** in addition to email and password (FR-AUTH-07) | — | M6 |
| C3 | **Medicine planner and in-app notifications.** A daily dose plan built only from the doctor's prescription (FR-REM-03), and notifications inside the app for patients and staff (FR-NTF) | — | M6 |
| C4 | **AI assistant, without medical advice.** Booking by chat, clinic questions, restating the doctor's own instructions in plain words, and staff helpers, through tools that call existing use cases with the user's own permissions. It never diagnoses, suggests drugs or doses, or interprets results. Behind an LLM gateway: Groq first, switchable (ADR-0013) (FR-AI) | §6.3 "AI diagnosis or clinical decision support" stays a non-goal; principle 6 unchanged | M7 |
| C5 | **One consolidated MediEase invoice per clinic:** the subscription, plus the clinic's actual WhatsApp usage, plus a MediEase markup on that usage. Each clinic sends from its own WhatsApp number; usage is metered per clinic (ADR-0014) (FR-BIL-WA) | Principle 4 "no per-message charges" and §12 "subscription only" | M8 (designed in M6, built later) |
| C6 | Pharmacy and clinic drug inventory stays a non-goal for now; it is a backlog candidate after the pilot | — | — |

Clinical safety is unchanged: MediEase never suggests diagnoses, doses or drugs (principle 6), and
clinical content never reaches logs, analytics or a third-party model except what a feature
explicitly sends under ADR-0013's rules.

---

## 1. Summary

Small independent clinics in India run their practice on personal WhatsApp, phone calls and paper
registers. Appointments arrive as messages, patient history lives in a register or in the doctor's
memory, and follow-ups, vaccinations and medicine instructions depend on someone remembering.

MediEase is a lightweight, WhatsApp-native clinic operating system for one-to-four-doctor practices.
It gives the clinic a single place where a patient exists — booking, a daily queue, a searchable
visit record and a digital prescription — and it reaches the patient on the channel they already
use: a web link and WhatsApp/SMS messages, with no app to install.

The product's differentiated wedge is **the patient side of the visit**: a prescription the patient
can re-read with dosage, dilution and diet instructions, and a follow-up reminder that actually
arrives. Those capabilities exist in the market today only at price points our segment has not
adopted (see §5). MediEase delivers them at a flat **₹999 per clinic per month**.

## 2. Problem

### 2.1 What happens today

An appointment request arrives on the doctor's or receptionist's personal WhatsApp, or as a phone
call during consultation hours. It is written in a register or held in someone's head. The patient
is seen, is given a prescription and a verbal explanation, and then leaves the system entirely.
There is no searchable record at the next visit, no queue anyone can see, and no mechanism that
brings the patient back.

### 2.2 The four recurring failures (Phase 1 evidence)

| # | Failure | Evidence (Phase 1 conversation IDs) |
|---|---|---|
| P1 | Appointment coordination is scattered across WhatsApp and phone calls | 7 of 14 clinics (A7–A13) |
| P2 | Patient records are not retrievable during a consultation | A11, A12 |
| P3 | Post-visit follow-up depends on memory; vaccination due dates are missed | A3, A14 |
| P4 | Medicine instructions are delivered once and lost (dosage, dilution, storage, diet) | A3, A6, A14 |

### 2.3 Why it matters

In a one-to-four-doctor clinic the coordination load falls on the doctor or a single front-desk
person — the practice's scarcest resource. A missed follow-up is a consultation that was never
billed; a misunderstood prescription is a treatment that fails, which in a referral-driven local
practice is a reputational cost the doctor pays directly. The problem recurs with every patient,
every day, and grows with volume.

### 2.4 What Phase 1 did **not** prove

No clinic in our sample has named a rupee figure. Evidence is strong on problem existence,
recurrence and feature demand (B4–B7), and unproven on willingness to pay. **The first commercial
objective of this product is to convert that unknown into a fact** (see §12).

## 3. Target segment

**In scope:** independent clinics and small specialty hospitals with **one to four doctors**, no
practice-management software in use, coordinating appointments through personal WhatsApp and
phone, with patient volume the owner can no longer hold in memory.

Typical shapes: single-specialty clinics (homoeopathy, paediatrics, physiotherapy), small
multi-specialty hospitals (e.g. dental + gynaecology), diagnostic-plus-consultation practices.

**Out of scope, deliberately:**

- Large hospitals and chains — procurement-led buying, already on hospital information systems.
- Pharmacies and medical stores — owned by Marg and Reckon.
- Very low-volume solo practices where manual still works (e.g. A2) — no felt pain.

**Segment boundary:** the determinant is *whether the operation has outgrown one person's memory*,
not company size.

## 4. Users and personas

| ID | Persona | Who | Primary jobs-to-be-done | Surface |
|---|---|---|---|---|
| U1 | **Patient / parent** | Clinic patient or parent of a paediatric patient; uses WhatsApp daily; will not install an app | Book without phoning in clinic hours; re-read prescription instructions; receive follow-up and vaccination reminders | Patient web links + WhatsApp/SMS |
| U2 | **Doctor** | Practice owner and clinical decision-maker; the buyer; time-poor | See patient history in seconds; write a digital prescription with instructions; see today's queue; zero training | Clinic dashboard — doctor view |
| U3 | **Front desk / compounder** | Often the only admin staff; handles incoming calls and messages | Register patients; convert requests into confirmed slots; run the day's queue; avoid double-booking | Clinic dashboard — front-desk view |
| U4 | **Clinic owner / admin** | Proprietor of a multi-doctor clinic (e.g. A13) | Manage doctors, staff and permissions; see volume and follow-up compliance | Clinic dashboard — admin view |
| U5 | **MediEase ops team** | Us | Create and configure a clinic in minutes; import patients; see whether a clinic is actually using the product | Internal ops console |

**Persona note — the doctor is buyer, user and bottleneck at once.** Any flow that costs a doctor
more than a few minutes of learning will fail regardless of price.

## 5. Competitive context (summary)

Figures as published on vendors' official pricing pages, September 2026. Re-verify before pricing
decisions. Full analysis: Phase 1 report §5.2.

| Alternative | Published price | Why our segment has not adopted it |
|---|---|---|
| WhatsApp + phone + paper | ₹0 | This is the real incumbent; any product must beat free-and-familiar on day one |
| Practo Ray | ₹999–₹1,999 / month (+1.8–2% on payments) | Marketplace- and Practo-app-centric; none of 14 clinics had adopted it |
| ring2doc | Free tier; Silver ₹1,199 / month | Closest match; newer, limited distribution |
| Lybrate Cube | ₹799–₹888 / month (1 clinic) | General suite; not built around patient-side clarity |
| Eka Care | ₹2,999–₹27,999 / month | WhatsApp prescription delivery exists only from ₹5,999 / month |
| Hospital-grade HMS | ₹25,000–₹75,000 one-time | Built for in-patient/insurance; wrong shape and revenue model |

**Positioning:** the patient-communication capability clinics described exists, but not at a price
a one-to-four-doctor clinic in our sample will pay. MediEase ships it as a core feature at ₹999.

## 6. Goals, non-goals and principles

### 6.1 Product goals (MVP)

| ID | Goal | Measured by |
|---|---|---|
| G1 | A clinic can run its whole day's bookings and queue in MediEase | ≥ 80% of the pilot clinic's visits have an appointment record |
| G2 | Patients can re-read their prescription after leaving | ≥ 50% of issued prescription links opened within 24 h |
| G3 | Follow-ups stop depending on memory | ≥ 90% of scheduled reminders delivered; follow-up return rate tracked |
| G4 | Onboarding costs a clinic less than an hour | Clinic live end-to-end in < 60 minutes |
| G5 | Clinics keep using it | Pilot clinic still booking through MediEase on day 14 and day 30 |

### 6.2 Business goals (Phase 2)

- B-1: Two named clinics on a **paid** ₹999/month pilot within 30 days of Phase 2 start.
- B-2: A refusal at ₹999 is recorded as a finding, with the stated reason.
- B-3: Recurring (subscription) revenue only — the programme does not count one-time payments.

### 6.3 Non-goals (MVP)

- In-patient / IPD management, bed management, insurance or TPA billing, NABH modules.
- A patient marketplace or doctor discovery.
- A patient mobile app to install (a web portal is in scope from v1.1, C1).
- Telemedicine / video consultation.
- Pharmacy inventory (a backlog candidate after the pilot, v1.1 C6).
- ABDM / ABHA integration (revisit post-pilot; see §14).
- Full billing and invoicing beyond the consolidated MediEase invoice (v1.1, C5).
- AI diagnosis or clinical decision support of any kind (the v1.1 assistant, C4, never does either).

### 6.4 Product principles

1. **Meet the clinic in WhatsApp, don't fight it.** Booking should still feel like sending a message.
2. **No patient install.** Every patient touchpoint is a link, a message or the web portal (v1.1, C1).
3. **Three taps for the doctor.** Any doctor action that needs training is a design defect.
4. **Predictable price.** One MediEase invoice: the flat subscription plus the clinic's WhatsApp
   usage at cost plus a stated markup (v1.1, C5); nothing else per message or per patient.
5. **The clinic owns its patients.** No MediEase-branded marketplace between clinic and patient.
6. **Clinical content is the doctor's.** MediEase formats, stores and delivers; it never suggests
   diagnoses, doses or drugs.

## 7. Scope and prioritisation

P0 = required for the MVP to be usable. P1 = next, once design partners are onboard.
P2 = later, closer to paid conversion. Priorities match the Phase 1 report §8.

| # | Capability | Priority | Requirement group | Phase 1 evidence |
|---|---|---|---|---|
| 1 | Appointment booking + daily queue | P0 | FR-APT, FR-QUE | A7–A13 |
| 2 | Patient record with visit history (incl. lookup by phone/name) | P0 | FR-PAT, FR-VIS | A11, A12 |
| 3 | Digital prescription with patient-readable instructions | P0 | FR-RX | A3, A6, A14 |
| 4 | Automated follow-up reminders (WhatsApp / SMS) | P0 | FR-REM, FR-MSG | A3, A14 |
| 5 | Clinic, doctor and staff setup with role-based access | P0 | FR-ORG, FR-AUTH | A13 |
| 6 | Clinic-owned booking / query landing page | P1 | FR-PUB | B4–B7 |
| 7 | Vaccination schedule tracking and due-date alerts | P1 | FR-VAX | A3 |
| 8 | Broadcast announcements to patient groups | P1 | FR-BRD | A1 |
| 9 | Advanced patient search and filters | P1 | FR-PAT-07 | A11, A12 |
| 10 | Specialty templates (Dental, Gynaecology, Physiotherapy, Homoeopathy, Paediatrics) | P1 | FR-TPL | A13 |
| 11 | Billing and payment history | P2 | FR-BIL | — |
| 12 | Analytics: volume, follow-up compliance, no-show rate | P2 | FR-ANL | — |
| — | Internal ops console | P0 (internal) | FR-OPS | Onboarding < 60 min |
| — | Audit log | P0 (compliance) | FR-AUD | DPDP |

## 8. Functional requirements

Conventions: each requirement has a stable ID. "Must" = P0 acceptance. Acceptance criteria are
written so they can become automated tests. Detailed behaviour lives in `docs/specs/`.

### 8.1 Identity, access and organisation — `FR-AUTH`, `FR-ORG`

| ID | Requirement | Priority |
|---|---|---|
| FR-ORG-01 | The ops team can create a **Clinic** (name, address, phone, timezone default `Asia/Kolkata`, specialties, working hours). | P0 |
| FR-ORG-02 | A clinic has one or more **Doctors**, each with name, qualification, and **medical council registration number** (printed on prescriptions). | P0 |
| FR-ORG-03 | A clinic has **Staff users** with exactly one role per clinic: `OWNER`, `DOCTOR`, `FRONT_DESK`. | P0 |
| FR-ORG-04 | The owner can invite, deactivate and change the role of staff. Deactivation takes effect on the next request. | P0 |
| FR-AUTH-01 | Staff sign in with phone number or email + password. Passwords are hashed with Argon2id. | P0 |
| FR-AUTH-02 | Sessions use short-lived access tokens and rotating refresh tokens in `HttpOnly`, `Secure`, `SameSite=Lax` cookies. | P0 |
| FR-AUTH-03 | Every API request is authorised against role **and** clinic membership; cross-clinic access is impossible by construction (see ADR-0003). | P0 |
| FR-AUTH-04 | Sign-in is rate-limited and locks for 15 minutes after 5 consecutive failures. | P0 |
| FR-AUTH-05 | Password reset by one-time code sent through the messaging port. | P1 |
| FR-AUTH-06 | OTP-only sign-in for doctors. | P1 |

**Permission matrix (P0):**

| Action | OWNER | DOCTOR | FRONT_DESK | OPS (platform) |
|---|---|---|---|---|
| Manage clinic settings, staff | ✅ | — | — | ✅ |
| Register / edit patient demographics | ✅ | ✅ | ✅ | — |
| Book / reschedule / cancel appointment | ✅ | ✅ | ✅ | — |
| Move queue status | ✅ | ✅ | ✅ | — |
| View clinical notes and prescriptions | ✅ | ✅ | ❌ (view "prescription issued" flag only) | ❌ |
| Write visit notes, issue prescription | ✅ if also a doctor | ✅ | ❌ | ❌ |
| Schedule follow-up reminder | ✅ | ✅ | ✅ | — |
| View usage metrics | ✅ | ✅ | — | ✅ (aggregate only) |

> Ops users never see clinical content. Support access to a clinic's data requires an explicit,
> time-boxed, audited grant from the clinic owner (FR-OPS-05).

### 8.2 Patients — `FR-PAT`

| ID | Requirement | Priority |
|---|---|---|
| FR-PAT-01 | Register a patient with name, phone (E.164), sex, date of birth *or* age, optional guardian name and guardian phone. | P0 |
| FR-PAT-02 | Phone is the primary lookup key. Registering a phone that already exists in the clinic shows the existing patient(s) — family members may share a phone. | P0 |
| FR-PAT-03 | Each patient gets a clinic-scoped human-readable ID (e.g. `ME-0142`). | P0 |
| FR-PAT-04 | Look up patients by phone, patient ID or name prefix; results in < 500 ms for 10,000 patients. | P0 |
| FR-PAT-05 | Record communication consent (WhatsApp / SMS), language preference (English / Hindi at MVP), and opt-out status. | P0 |
| FR-PAT-06 | For patients under 18, the guardian is the contact of record and the consent is recorded against the guardian. | P0 |
| FR-PAT-07 | Advanced search: filters by last visit date, doctor, pending follow-up, tags. | P1 |
| FR-PAT-08 | Bulk import from CSV by the ops team, with a dry-run report of duplicates and invalid rows. | P0 (internal) |

**Acceptance (FR-PAT-02):** Given a clinic with a patient on `+919876543210`, when front desk
enters `98765 43210`, then the phone is normalised to `+919876543210` and the existing patient is
offered before a new record can be created.

### 8.3 Appointments — `FR-APT`

| ID | Requirement | Priority |
|---|---|---|
| FR-APT-01 | Each doctor has a weekly schedule (sessions per weekday, slot length, max patients per session) and date-specific exceptions (leave, extra session). | P0 |
| FR-APT-02 | Two booking modes per clinic: **time slots** or **token-only** (walk-in style, ordered numbers per session). Many Indian clinics run tokens. | P0 |
| FR-APT-03 | Front desk books for a patient in ≤ 3 interactions from the queue screen. | P0 |
| FR-APT-04 | The system prevents double-booking a slot and exceeding session capacity, including under concurrent requests. | P0 |
| FR-APT-05 | Reschedule and cancel with a reason; history is retained. | P0 |
| FR-APT-06 | Booking confirmation is sent to the patient (if consented) via the messaging port. | P0 |
| FR-APT-07 | Appointment sources are recorded: `FRONT_DESK`, `PHONE`, `WHATSAPP`, `PUBLIC_PAGE`, `WALK_IN`. | P0 |
| FR-APT-08 | Appointment reminder before the visit, configurable (default: evening before + 2 hours before). | P1 |

**Acceptance (FR-APT-04):** Given one remaining slot, when two booking requests for it arrive
concurrently, then exactly one succeeds and the other receives `APT_SLOT_TAKEN` (HTTP 409).

### 8.4 Daily queue — `FR-QUE`

| ID | Requirement | Priority |
|---|---|---|
| FR-QUE-01 | A per-doctor, per-day queue view showing token/slot, patient, status and wait time. | P0 |
| FR-QUE-02 | Statuses: `BOOKED → ARRIVED → IN_CONSULTATION → COMPLETED`, plus `NO_SHOW` and `CANCELLED`. Invalid transitions are rejected. | P0 |
| FR-QUE-03 | The queue updates for all open screens within 5 seconds without a manual refresh. | P0 |
| FR-QUE-04 | Walk-ins can be added directly to today's queue. | P0 |
| FR-QUE-05 | Marking `IN_CONSULTATION` opens the patient's visit screen for the doctor. | P0 |
| FR-QUE-06 | Patient-facing live token status link ("you are 3rd in line"). | P1 |

### 8.5 Visits and clinical record — `FR-VIS`

| ID | Requirement | Priority |
|---|---|---|
| FR-VIS-01 | A visit is created from an appointment (or directly for walk-ins) and belongs to one doctor. | P0 |
| FR-VIS-02 | The doctor records chief complaint, vitals (optional fields), findings, diagnosis (free text) and notes. | P0 |
| FR-VIS-03 | The patient's previous visits and prescriptions are visible on the same screen, newest first, loaded in < 1 s. | P0 |
| FR-VIS-04 | Attach files (images/PDF of reports) up to 10 MB each. | P1 |
| FR-VIS-05 | A visit becomes read-only 24 hours after completion; later changes are **addenda** with author and timestamp. | P0 |

### 8.6 Digital prescription — `FR-RX` (differentiated wedge)

| ID | Requirement | Priority |
|---|---|---|
| FR-RX-01 | The doctor adds medicines with: name, form, strength, dose, frequency (e.g. 1-0-1), timing relative to food, duration, and quantity. | P0 |
| FR-RX-02 | Each medicine can carry **patient instructions**: dilution/preparation, storage, special warnings, in structured fields plus free text. | P0 |
| FR-RX-03 | Prescription-level advice: diet, activity, follow-up date, and "when to return immediately" warnings. | P0 |
| FR-RX-04 | Instructions render in the patient's language preference (English / Hindi) using structured phrases; free text is shown as written. | P0 |
| FR-RX-05 | The doctor can save and reuse **favourites** (a medicine with its usual instructions) and **Rx templates**. | P0 |
| FR-RX-06 | Issuing a prescription produces (a) a printable A5/A4 PDF with clinic letterhead, doctor name, qualification and registration number, and (b) a **patient link** delivered via WhatsApp/SMS. | P0 |
| FR-RX-07 | The patient link shows a mobile-first page: each medicine as a card with *when*, *how much*, *how to prepare*, *how long*. No login; protected per FR-RX-08. | P0 |
| FR-RX-08 | Patient links are signed, single-purpose and expire after 90 days; opening requires confirming the last 4 digits of the registered phone. Every open is logged. | P0 |
| FR-RX-09 | An issued prescription is immutable. Corrections create a new version that supersedes the old one; the patient link shows the latest version and says it was updated. | P0 |
| FR-RX-10 | MediEase does **not** suggest drugs, doses or interactions. The medicine name field autocompletes only from the clinic's own history and favourites. | P0 |

**Acceptance (FR-RX-07):** Given an issued prescription with "Syrup X, 5 ml, 1-0-1, after food,
5 days, shake well, dilute in 10 ml boiled cooled water", when the parent opens the link on a
360-px-wide phone, then each field is visible without horizontal scroll and the dilution
instruction appears under a "How to give" heading.

### 8.7 Follow-ups and reminders — `FR-REM`

| ID | Requirement | Priority |
|---|---|---|
| FR-REM-01 | When a prescription has a follow-up date, a follow-up reminder is scheduled automatically (default: 1 day before, 9:00 clinic time). | P0 |
| FR-REM-02 | Staff can schedule, edit or cancel a reminder manually for any patient. | P0 |
| FR-REM-03 | Medicine-course reminders (optional per prescription): daily at chosen times until the course ends. | P1 |
| FR-REM-04 | Reminders are never sent to opted-out patients, and never between 21:00 and 08:00 clinic time; due reminders in that window are deferred to 08:00. | P0 |
| FR-REM-05 | Every reminder has a visible status: `SCHEDULED`, `SENT`, `DELIVERED`, `READ`, `FAILED`, `CANCELLED`, `SKIPPED_NO_CONSENT`. | P0 |
| FR-REM-06 | Failed WhatsApp sends fall back to SMS once, if the patient consented to SMS. | P1 |
| FR-REM-07 | A "pending follow-ups" list shows patients whose follow-up date has passed without a visit. | P0 |

### 8.8 Messaging — `FR-MSG`

| ID | Requirement | Priority |
|---|---|---|
| FR-MSG-01 | All outbound messages go through one messaging port with adapters for WhatsApp Business Platform (Cloud API), SMS, and a console/dev adapter. | P0 |
| FR-MSG-02 | Business-initiated WhatsApp messages use **pre-approved templates** only (Meta requirement). Template names and variables are versioned in the repo. | P0 |
| FR-MSG-03 | Delivery status webhooks update message status idempotently. | P0 |
| FR-MSG-04 | Every message is stored with template, variables (redacted of clinical detail), channel, provider message ID and status. Message bodies never contain diagnosis or medicine names — only a link. | P0 |
| FR-MSG-05 | Inbound "STOP" (and Hindi equivalents) opts the patient out and confirms. | P0 |
| FR-MSG-06 | Per-clinic sender identity: MVP uses one MediEase WhatsApp number with the clinic name in every template; a clinic-owned number is P2. | P0 |
| FR-MSG-07 | Messaging cost per clinic is tracked internally (MediEase absorbs it under flat pricing). | P0 |

### 8.9 Public booking page — `FR-PUB` (P1)

| ID | Requirement | Priority |
|---|---|---|
| FR-PUB-01 | Each clinic gets a public page at `/c/{clinic-slug}` with name, address, map link, hours, doctors and a booking/query form. | P1 |
| FR-PUB-02 | The form creates a **booking request** that front desk confirms or declines; it does not auto-book in MVP. | P1 |
| FR-PUB-03 | Phone verification by OTP before a request is accepted; rate-limited per phone and IP. | P1 |
| FR-PUB-04 | The page link is shareable to WhatsApp status and Google Business Profile. | P1 |

### 8.10 P1/P2 capabilities (outline — specified when scheduled)

- **FR-VAX** — Vaccination schedules: per-child schedule from a configurable template (the clinic
  maintains its own schedule; MediEase ships no clinical defaults), due-date reminders.
- **FR-BRD** — Broadcasts: send an approved announcement template (e.g. health camp) to a tagged
  patient group, respecting consent and quiet hours.
- **FR-TPL** — Specialty templates: visit-form fields and Rx templates per specialty.
- **FR-BIL** — Billing: consultation fee capture, receipt, daily collection summary.
- **FR-ANL** — Analytics: visits per day, no-show rate, follow-up return rate, reminder delivery.

### 8.11 Internal ops console — `FR-OPS`

| ID | Requirement | Priority |
|---|---|---|
| FR-OPS-01 | Create clinic, doctors and owner account in one guided flow. | P0 |
| FR-OPS-02 | Import patients from CSV (FR-PAT-08). | P0 |
| FR-OPS-03 | Clinic health view: last login, appointments this week, prescriptions issued, reminders sent/failed. No clinical content. | P0 |
| FR-OPS-04 | Onboarding checklist per clinic with timestamps (to measure G4). | P0 |
| FR-OPS-05 | Support access requires an owner-approved, time-boxed grant; every access is audited. | P1 |

### 8.12 Audit — `FR-AUD`

| ID | Requirement | Priority |
|---|---|---|
| FR-AUD-01 | Record who did what, when, to which record, for: sign-in, staff changes, patient create/edit/merge, visit and prescription create/issue/addendum, consent changes, patient-link opens, data exports, support access. | P0 |
| FR-AUD-02 | Audit entries are append-only and are not editable through any API. | P0 |
| FR-AUD-03 | The owner can view and export the clinic's audit log. | P1 |

### 8.13 v1.1 additions — `FR-AUTH-07`, `FR-PRT`, `FR-NTF`, `FR-AI`, `FR-BIL-WA`

Detailed behaviour is specified per phase in `docs/specs/` (one spec per feature, SPECS.md).

| ID | Requirement | Priority |
|---|---|---|
| FR-AUTH-07 | Staff and patients can sign in with Google (OpenID Connect) as well as email and password. A Google sign-in never creates staff access by itself: it signs in an existing staff user whose verified email matches, or a patient account. | P1 |
| FR-PRT-01 | A patient creates an account with Google or email and password; the account holds no clinic data until it is linked. | P1 |
| FR-PRT-02 | An account is linked to a clinic's patient record only by proof the clinic gave the patient: a single-use clinic invite, or a prescription link after its last-4-digit check. One account may be linked to records in several clinics; each clinic's data stays separate. | P1 |
| FR-PRT-03 | The patient sees, per linked clinic: upcoming and past appointments, issued prescriptions (the patient page and PDF), reminders and their status, and the medicine plan. Never the doctor's notes or diagnosis unless a later spec says so. | P1 |
| FR-PRT-04 | The portal is mobile-first (360 px), in English and Hindi, WCAG 2.1 AA. | P1 |
| FR-REM-03 | (existing) Medicine-course plan: daily times derived only from each prescribed line's frequency, timing and days, shown to the patient and optionally reminded in the app. | P1 |
| FR-NTF-01 | In-app notifications for patients (appointment confirmed or moved, prescription ready, medicine due, follow-up due) and staff (booking request, failed message), with read state. | P1 |
| FR-AI-01 | A patient or staff assistant answers through tools that call existing use cases with the user's own permissions; it can book, reschedule and cancel by chat after an explicit confirmation step. | P1 |
| FR-AI-02 | The assistant never gives medical advice, diagnoses, suggests or changes drugs or doses, or interprets results; such questions get a fixed referral to the clinic. Guard-rail tests prove it. | P0 for FR-AI |
| FR-AI-03 | The model is reached only through an LLM gateway port; the provider (Groq first, then DeepInfra, OpenAI or another OpenAI-compatible API) is a setting, not code. | P1 |
| FR-BIL-WA-01 | Each clinic sends WhatsApp messages from its own number, connected through Meta's Embedded Signup; credentials, templates and webhook events are kept per clinic. | P2 |
| FR-BIL-WA-02 | Every billable WhatsApp event is written to an append-only usage ledger per clinic (message, category, time, billing period, Meta cost, markup); one MediEase invoice per clinic per month adds the subscription. No clinic's usage can appear on another's invoice. | P2 |

## 9. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | p95 API latency < 300 ms for reads, < 500 ms for writes at pilot scale (≤ 50 clinics, ≤ 500 visits/day total). |
| NFR-02 | Performance | Clinic dashboard first load < 3 s on a 4G connection; patient prescription page < 2 s on 3G, < 200 KB transferred. |
| NFR-03 | Availability | 99.5% monthly during clinic hours (08:00–22:00 IST) for the pilot. |
| NFR-04 | Durability | Automated daily database backups retained 30 days, point-in-time recovery ≤ 24 h RPO; restore tested monthly. RTO ≤ 4 h. |
| NFR-05 | Security | TLS 1.2+ everywhere; encryption at rest for database and file storage; secrets only from the environment. |
| NFR-06 | Security | OWASP ASVS Level 2 as the review baseline; dependency scanning in CI. |
| NFR-07 | Privacy | Data hosted in India. Clinical content never appears in logs, message bodies, analytics events or error reports. |
| NFR-08 | Multi-tenancy | Every tenant-owned row carries `clinic_id`; every query is scoped by the tenancy layer; automated tests prove cross-tenant isolation. |
| NFR-09 | Usability | Core flows usable on a 1366×768 desktop and a 360-px phone; front desk can book without training. |
| NFR-10 | Accessibility | WCAG 2.1 AA for patient-facing pages. |
| NFR-11 | Localisation | English UI for staff at MVP; patient-facing pages and messages in English and Hindi. All times stored in UTC, shown in clinic timezone. |
| NFR-12 | Observability | Structured JSON logs with `request_id`, `clinic_id` (never patient data); correlation from browser → API → worker → provider. See [DEBUGGING.md](DEBUGGING.md). |
| NFR-13 | Reliability | Reminder jobs are at-least-once with idempotent sends; a crashed worker never loses or duplicates a patient-visible message. |
| NFR-14 | Maintainability | Hexagonal architecture; domain layer has no framework imports; ≥ 80% unit-test coverage of domain and application layers. |
| NFR-15 | Portability | Whole stack runs locally with `make up`; no cloud-only dependency is required for development. |
| NFR-16 | Cost | Infrastructure + messaging cost per clinic < ₹250/month at pilot scale (tracked, see FR-MSG-07). |

## 10. Compliance and clinical safety (requirements view)

Details and controls: [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md). This section is a
product view, not legal advice; obligations must be confirmed with counsel before launch.

- **Roles under the DPDP Act, 2023.** The clinic is the *Data Fiduciary*; MediEase acts as its
  *Data Processor* under a written agreement. The DPDP Rules were notified on 14 November 2025 with
  an 18-month phased timeline; the product is built to the end-state obligations from day one.
- **Notice and consent.** The clinic captures patient consent for communication at registration
  (FR-PAT-05). MediEase provides a notice template the clinic can adopt.
- **Children.** The Rules require verifiable parental consent for children's data, with exemptions
  that include healthcare purposes. Paediatric clinics are core users (A3); the guardian model
  (FR-PAT-06) is built regardless of how the exemption is ultimately applied.
- **Data principal rights.** Access, correction and erasure requests are handled by the clinic with
  tooling from MediEase, within the statutory response window. Erasure respects any medical-record
  retention the clinic is legally required to keep.
- **Breach notification.** Incident runbook covers notifying the clinic without delay so it can
  meet its obligations to the Board and affected individuals.
- **Prescription content.** Prescriptions show the doctor's name, qualification and registration
  number, and the clinic's details. MediEase never generates clinical recommendations (FR-RX-10).
- **Messaging.** WhatsApp business-initiated messages use approved templates; SMS requires DLT
  registration of sender ID and templates in India (TRAI).

## 11. Success metrics

### 11.1 North-star

**Weekly active clinics** — clinics where ≥ 1 doctor issued ≥ 1 prescription on ≥ 3 days in the week.

### 11.2 Pilot scorecard

| Metric | Target | Source |
|---|---|---|
| Time to first live booking after onboarding starts | < 60 min | FR-OPS-04 timestamps |
| Share of visits with an appointment record | ≥ 80% | appointments vs visits |
| Prescriptions issued digitally / visits | ≥ 60% by day 30 | visits, prescriptions |
| Prescription link open rate (24 h) | ≥ 50% | link open audit events |
| Reminder delivery rate | ≥ 90% | message statuses |
| Follow-up return rate (visit within 3 days of follow-up date) | Baseline in month 1, then +20% | reminders, visits |
| Day-14 and day-30 retention | Clinic still booking | appointments |
| Paid conversion | 2 clinics at ₹999 within 30 days | billing ledger |

### 11.3 Product analytics events (no PII, no clinical content)

`clinic_onboarding_step_completed`, `appointment_created`, `queue_status_changed`,
`visit_completed`, `prescription_issued`, `prescription_link_opened`, `reminder_scheduled`,
`message_status_changed`, `patient_opted_out`, `public_booking_requested`.
Properties are limited to IDs, enums, counts and durations.

## 12. Pricing and packaging (hypothesis to test)

| Plan | Price | Includes |
|---|---|---|
| Starter | ₹999 / clinic / month | 1–2 doctors, unlimited staff, patients, appointments, prescriptions; messaging included |
| Clinic | ₹1,499 / clinic / month | 3–4 doctors, everything in Starter |
| Design-partner pilot | Free for 14 days | Full product, in-person onboarding |

- Subscription plus WhatsApp usage at cost and a stated markup, on one MediEase invoice (v1.1, C5).
- Payment by UPI AutoPay / e-mandate is **manual in MVP** (invoice + UPI); automated billing is P2.
- **First test:** offer the paid pilot to Aarogya Hospital (A13) and Apollo Diagnostic (A10), with
  Arvind Homoeopathy (A1) if either declines. Ask for payment, not feedback.

## 13. Release plan

Milestones are delivered one at a time under the approval gates in [CLAUDE.md](../CLAUDE.md).
Detailed task breakdown: [TASKS.md](../TASKS.md).

| Milestone | Outcome | Requirement coverage | Exit criterion |
|---|---|---|---|
| **M0 Foundation** | Repo, containers, config, logging, health/readiness, CI | NFR-12, NFR-15 | `make up` → `/health` and `/ready` green; CI green |
| **M1 Identity & tenancy** | Clinics, staff, roles, auth, audit, ops onboarding flow | FR-ORG, FR-AUTH-01..04, FR-AUD-01..02, FR-OPS-01, 04 | Cross-tenant isolation tests pass |
| **M2 Patients** | Registration, lookup, consent, CSV import | FR-PAT-01..06, 08 | 10k-patient lookup < 500 ms |
| **M3 Appointments & queue** | Schedules, booking, token mode, live queue | FR-APT-01..07, FR-QUE-01..05 | Concurrency test passes; front desk books in ≤ 3 interactions |
| **M4 Visits & prescriptions** | Visit record, Rx builder, PDF, patient link | FR-VIS-01..03, 05, FR-RX-01..10 | Patient page acceptance test on 360 px |
| **M5 Messaging & reminders** | Messaging port + adapters, job worker, reminders, opt-out | FR-MSG, FR-REM-01, 02, 04, 05, 07, FR-APT-06 | End-to-end reminder delivered via WhatsApp sandbox (done in code; the live test is pending L-01, L-02) |
| **M6 MVP demo: clinic and patient experience** (v1.1) | Design system, role dashboards, patient portal with Google and email sign-in, medicine planner, in-app notifications, public booking page | FR-AUTH-07, FR-PRT, FR-REM-03, FR-NTF, FR-PUB | Every journey demonstrable on the local stack; `make e2e` green |
| **M7 AI assistant and pitch** (v1.1) | LLM gateway (Groq first), patient and staff assistant with tools, animated landing page | FR-AI | Booking by chat and the guard-rail tests pass |
| **M8 Multi-clinic WhatsApp and consolidated billing** (v1.1) | Embedded Signup per clinic, per-clinic templates and webhooks, usage ledger, one MediEase invoice | FR-BIL-WA | Two clinics' usage billed separately with no mixing |
| **M9 Pilot hardening** | Backups, monitoring, ops health view, security review, deploy | NFR-03..07, FR-OPS-03 | Restore drill done; security checklist signed |
| **— Pilot launch —** | Two clinics live | G1–G5 | Scorecard §11.2 tracked weekly |
| **M10+** | Vaccination, broadcasts, specialty templates, search, analytics, pharmacy inventory | FR-VAX, FR-BRD, FR-TPL, FR-PAT-07, FR-ANL | Driven by pilot feedback |

## 14. Risks, assumptions and open questions

### 14.1 Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Clinics specify features but will not pay | Fatal | Paid pilot is the first test (§12); treat refusal as data |
| Adoption dies at onboarding | High | < 60 min onboarding; ops team migrates data; day-14 usage check |
| Distribution cost vs ₹999 ticket | High | Test channels in Phase 2: clinic associations, medical reps, doctor referrals |
| WhatsApp template rejection or number quality drop | Medium | Utility-only templates, conservative sending, SMS fallback, quality monitoring |
| Messaging cost growth | Medium | Link-only messages, per-clinic cost tracking (FR-MSG-07), prefer free service-window replies |
| Health-data breach | Severe | Tenancy isolation tests, encryption, audit, least privilege, no clinical data in logs/messages |
| Doctor finds Rx entry slower than paper | High | Favourites and templates (FR-RX-05), keyboard-first UI, measure time-to-issue |
| Regulatory interpretation changes | Medium | Counsel review before pilot; compliance items tracked in TASKS.md |

### 14.2 Assumptions

- A1: Patients will open a link sent on WhatsApp without installing anything.
- A2: One shared MediEase WhatsApp number with clinic-named templates is acceptable to clinics at MVP.
- A3: Pilot clinics have at least one desktop or laptop at the front desk and a smartphone for the doctor.
- A4: English staff UI is acceptable for pilot clinics; Hindi is needed for patients.
- A5: The pilot runs on a single-region deployment in India.

### 14.3 Open questions

1. Will clinics accept a patient surface that is only WhatsApp + web link?
2. In multi-doctor practices, who authorises a recurring payment — doctor or owner?
3. Does prescription clarity drive adoption on its own, or only once booking and records are in place?
4. How many "manual is fine" businesses reverse on a second conversation (as A5 → B6 did)?
5. Token mode vs time slots — which do pilot clinics actually run? (Built both; measure.)
6. Is a clinic-owned WhatsApp number a buying criterion? (Currently P2.)
7. When should ABDM/ABHA integration enter the roadmap?

## 15. Glossary

See [GLOSSARY.md](GLOSSARY.md). Key terms: *Clinic* (tenant), *Session* (a doctor's block of
consultation time), *Token* (queue number within a session), *Visit* (one consultation),
*Prescription* (issued, immutable Rx document), *Patient link* (signed, expiring URL),
*Reminder* (scheduled outbound message), *Template* (Meta-approved WhatsApp message format).

## 16. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 15 Sep 2026 | First complete PRD from Phase 1 validation and Phase 2 readiness work |
