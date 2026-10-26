# MediEase — Product Requirements Document

| Field | Value |
|---|---|
| Product | MediEase (working name) |
| Document owner | Product team (Sitare University Startup Program, Group 1) |
| Status | v1.3 — M7 split into the assistant and verified uploads, approved by the developer on 27 Oct 2026 (§0.0) |
| Last updated | 27 October 2026 |
| Target segment | Small clinics with 2–5 doctors and staff (solo practitioners supported), India; medical stores later |
| Related documents | [ARCHITECTURE.md](ARCHITECTURE.md) · [DATA_MODEL.md](DATA_MODEL.md) · [API.md](API.md) · [../SPECS.md](../SPECS.md) · [../TASKS.md](../TASKS.md) · [SECURITY_AND_COMPLIANCE.md](SECURITY_AND_COMPLIANCE.md) |

> **How to read this document.** Sections 1–5 explain *why* we are building MediEase and *for whom*.
> Sections 6–9 define *what* it must do, with stable requirement IDs (`FR-…`, `NFR-…`) that specs,
> tasks, tests and commits reference. Sections 10–14 cover *how we will know it works* and *how it
> ships*. Anything describing *how the code is built* lives in the architecture documents, not here.

---

## 0.0 Changes in v1.3 (27 October 2026)

Approved by the developer after the M7 architecture review
(`docs/milestones/M7-architecture-review.md`, decisions D1–D7). Wins over §0 and §0.1 where they
differ.

| # | Change | Replaces | Built in |
|---|---|---|---|
| C15 | **M7a: the assistant.** C4 as designed, plus FR-AI-04: the assistant explains only a prescription the user picked, by restating its database record. New prescriptions print the MediEase mark, a verification code and a QR code (FR-RX-11, ADR-0023) | M7 "AI assistant and pitch"; the animated landing-page polish moves to the backlog | M7a |
| C16 | **M7b: verified prescription uploads.** A patient, family member or representative can upload a MediEase prescription (or type its code) so the assistant can explain it. The file is scanned (ClamAV), only its identifier is read, the identifier is verified against the database and the uploader's own access (a representative passes the prescription's last-4 check and gets that one prescription only), and the file is deleted. Arbitrary external prescriptions are never accepted, and nothing read from a file is used as clinical information (FR-UPL, NFR-20, ADR-0023) | Spec visit-attachments §11 "patients uploading, OCR, virus scanning" out of scope (now in, for this one purpose; OCR stays out) | M7b |

Principle 6 and the §6.3 non-goal on clinical decision support are unchanged: the assistant
restates the doctor's record and never interprets or advises.

---

## 0. Changes in v1.2 (22 October 2026)

Decided by the developer during the M6 planning, after reviewing what building M0–M5 taught us.
**Where any later section, or the v1.1 table below, says otherwise, this section wins.**

**Why the direction changed.** MediEase is a *SaaS for small clinics* (2–5 doctors and staff) at an
aggressively low price, and Practo is a much bigger product with a different customer. Our answer to
Practo is not to copy it, but to be the cheapest, simplest system a small clinic can run its whole
day on, *plus* a free way for local patients to find that clinic and request a visit. Discovery
therefore exists to feed the clinic's own queue, not to sit between clinic and patient.

| # | Change | Replaces | Built in |
|---|---|---|---|
| C7 | **Patient discovery and booking requests.** A patient can search discoverable clinics (`ACTIVE`, verified and listed, FR-ONB-09) by **doctor name, clinic name or speciality** (plus city/PIN), open a public clinic or doctor profile, pick from slots generated from that doctor's own schedule, and send a **booking request**. The request reaches the clinic's front desk as a notification; the clinic **accepts or declines** it. Nothing is confirmed automatically (FR-DIS, FR-BKG) | §6.3 non-goal "A patient marketplace or doctor discovery"; principle 5 is reworded | M6b, M6c |
| C8 | **Verified clinic onboarding.** A clinic or doctor can apply on the website (self-service). The **application** has its own lifecycle (`PENDING → UNDER_REVIEW → APPROVED \| REJECTED`) while the MediEase team manually verifies it; approval creates the clinic through the same wizard ops use. Three things are kept apart: the application's status, the clinic's **operational status** (unchanged: `ONBOARDING → ACTIVE ↔ SUSPENDED`) and its **public visibility**. A clinic is discoverable only when it is `ACTIVE`, **verified** and **listed** (FR-ONB-02) | FR-ORG-01 as the only way to create a clinic | M6c |
| C9 | **Patient account with Google OAuth.** A patient signs up with Google (or email and password) and lands on a **fresh dashboard**: zero appointments, no prescriptions, no notifications, with one clear first action, *Find a doctor*. A patient account is global to MediEase; each clinic relationship is separate. A booking **accepted by a clinic** links the account to that clinic's patient record (staff-matched, never by phone alone) | C1: account linked *only* by clinic invite or prescription link | M6a (account and sign-in), M6b (dashboard, linking) |
| C10 | **Role-specific workspaces.** Owner, Doctor and Front Desk get different navigation, home screen and workflows, not one UI with different permissions (FR-UX). A doctor can book an appointment on behalf of a patient | Single shared dashboard | M6a |
| C11 | **Notification service with channels.** Features raise domain events; a notification service delivers them in-app, by WhatsApp, and later email/SMS, per recipient preference. WhatsApp is one adapter, not hard-wired into features (FR-NTF-02..06) | FR-NTF-01 only | M6a (core), M8 (per-clinic WhatsApp) |
| C12 | **Clinic billing in scope.** Consultation fees, procedures, discounts, cash/UPI/card recorded, receipts, outstanding dues, daily collection (FR-BIL-01..07). Insurance/TPA and payment-gateway collection stay out | §6.3 "Full billing" non-goal for clinics; FR-BIL P2 | M6d |
| C13 | **Inventory and medical stores.** Clinic stock inventory with batches and expiry (FR-INV), then a lightweight **medical-store workspace** that receives a patient's prescription by code and records dispensing (FR-PHA). Store and clinic data stay separate tenants | C6 "pharmacy and clinic drug inventory stays a non-goal" | M10+ |
| C14 | **SaaS packaging and landing page.** Subscription priced by clinic size, a 14-day trial, plan limits enforced, and a public landing page for clinics and patients with the clinic application as the main call to action (FR-SUB, FR-LND) | Single ₹999 plan; landing page only in M7 | M6c (page), M6d (plans) |

**Already specified earlier but never scheduled, now scheduled** (found while reconciling §13):

| Requirement | Why it matters | Now in |
|---|---|---|
| FR-APT-08 appointment reminders | Without it patients get follow-up reminders but no "visit tomorrow" message; drives no-shows | M6a |
| FR-AUTH-05 password reset | Patients and staff will lock themselves out | M6a |
| FR-QUE-06 live token status link | Standard in Indian clinics; cheap | M6b |
| FR-VIS-04 report attachments | Needed by diagnostic-plus-consultation clinics (A10) | M6d |
| FR-AUD-03 owner audit view | Trust for multi-doctor clinics | M6a |

**Also decided on 22 Oct 2026** (while reviewing the M6-P3 design):

- **No SMS OTP.** A booking request needs a signed-in patient account instead: Google, or email
  and password with a verified email (FR-PUB-03, FR-AUTH-08).
- **Practising owner.** One role per membership stays. An owner who practises is an `OWNER` with a
  linked doctor profile, gets an Owner / Doctor switch, and can be set up as Doctor 1 in the same
  onboarding step (FR-ORG-03, FR-UX-06, FR-ONB-08).
- **Application, operation and visibility are separate.** Application status, clinic status and
  public listing are three independent facts (FR-ONB). Approval by MediEase never makes a clinic
  public by itself.
- **Order.** M6a (auth, staff workspaces, notifications) → M6b (patient identity, portal, booking)
  → M6c (SaaS onboarding, verification, discovery) → M6d (billing, documents). Each is its own
  issue, branch and PR (ADR-0011); the open M6 issue #49 becomes M6a.

Clinical safety, the "clinical content never reaches logs or messages" rule, and the consent rules
are unchanged.

---

## 0.1 Changes in v1.1 (20 October 2026)

Decided by the developer after M5. Superseded by §0 where the two differ.

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

MediEase is a lightweight, WhatsApp-native clinic operating system for small practices of two to five doctors and staff (solo practitioners included).
It gives the clinic a single place where a patient exists — booking, a daily queue, a searchable
visit record and a digital prescription — and it reaches the patient on the channel they already
use: a web link and WhatsApp/SMS messages, with no app to install.

MediEase covers the clinic's whole day: appointments and queue, digital patient records, prescriptions
with dosage instructions, follow-up reminders, billing, staff management and, later, inventory. It is
sold as a **monthly SaaS subscription priced by clinic size**. Patients can sign up with Google, find
an approved clinic or doctor, and send a booking request that the clinic's front desk accepts or
declines. The initial focus is small clinics and independent doctors, with specialty hospitals and
medical stores to follow.

The product's differentiated wedge is **the patient side of the visit**: a prescription the patient
can re-read with dosage, dilution and diet instructions, and a follow-up reminder that actually
arrives. Those capabilities exist in the market today only at price points our segment has not
adopted (see §5). MediEase delivers them at an aggressively low monthly subscription sized to the clinic (§12).

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

**In scope:** independent clinics and small specialty hospitals with **two to five doctors and staff** (solo practitioners supported), no
practice-management software in use, coordinating appointments through personal WhatsApp and
phone, with patient volume the owner can no longer hold in memory.

Typical shapes: single-specialty clinics (homoeopathy, paediatrics, physiotherapy), small
multi-specialty hospitals (e.g. dental + gynaecology), diagnostic-plus-consultation practices.

**Out of scope, deliberately:**

- Large hospitals and chains — procurement-led buying, already on hospital information systems.
- Pharmacies and medical stores as a *primary* customer at MVP — owned by Marg and Reckon. A light
  prescription-receiving store workspace is planned later (v1.2, C13).
- Very low-volume solo practices where manual still works (e.g. A2) — no felt pain.

**Segment boundary:** the determinant is *whether the operation has outgrown one person's memory*,
not company size.

## 4. Users and personas

| ID | Persona | Who | Primary jobs-to-be-done | Surface |
|---|---|---|---|---|
| U1 | **Patient / parent** | Clinic patient or parent of a paediatric patient; uses WhatsApp daily; will not install an app; may be new to MediEase | Find a doctor by name, clinic or speciality; request a booking without phoning; re-read prescription instructions; receive follow-up and vaccination reminders; see appointments across clinics | Patient web portal (Google sign-in) + links + WhatsApp/SMS |
| U2 | **Doctor** | Practice owner and clinical decision-maker; the buyer; time-poor | See patient history in seconds; write a digital prescription with instructions; see today's queue; zero training | Clinic dashboard — doctor view |
| U3 | **Front desk / compounder** | Often the only admin staff; handles incoming calls and messages | Register patients; convert requests into confirmed slots; run the day's queue; avoid double-booking | Clinic dashboard — front-desk view |
| U4 | **Clinic owner / admin** | Proprietor of a multi-doctor clinic (e.g. A13) | Manage doctors, staff and permissions; see volume and follow-up compliance | Clinic dashboard — admin view |
| U5 | **MediEase ops team** | Us | Review and verify clinic applications; create and configure a clinic in minutes; import patients; see whether a clinic is actually using the product | Internal ops console |
| U6 | **Medical store (later)** | Small independent pharmacy near a clinic | Receive a patient's prescription by code; record what was dispensed; keep simple stock | Store workspace (M10+) |

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
a small clinic in our sample will pay. MediEase ships it as a core feature at a price sized to the clinic.

**Against Practo specifically:** Practo is larger and built around its own marketplace. MediEase is built
for clinics of 2–5 people: the clinic owns its patient relationship, there is **no commission, no ads
and no paid ranking**, and the price is deliberately lower. Discovery is a free feature that brings
patients to the clinic's own queue.

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

- B-1: Two named clinics on a **paid** pilot (₹999/month reference tier) within 30 days of Phase 2 start.
- B-2: A refusal at ₹999 is recorded as a finding, with the stated reason.
- B-3: Recurring (subscription) revenue only — the programme does not count one-time payments.

### 6.3 Non-goals (MVP)

- In-patient / IPD management, bed management, insurance or TPA billing, NABH modules.
- Marketplace features beyond free discovery: ratings/reviews, paid ranking, ads and per-booking commission (discovery itself is in scope, v1.2 C7).
- A patient mobile app to install (a web portal is in scope from v1.1, C1).
- Telemedicine / video consultation.
- Hospital-scale pharmacy/ERP, drug e-commerce and delivery (clinic stock inventory and a light medical-store workspace are in scope later, v1.2 C13).
- ABDM / ABHA integration (revisit post-pilot; see §14).
- Insurance/TPA billing and payment-gateway collection (simple clinic fee billing is in scope, v1.2 C12).
- AI diagnosis or clinical decision support of any kind (the v1.1 assistant, C4, never does either).

### 6.4 Product principles

1. **Meet the clinic in WhatsApp, don't fight it.** Booking should still feel like sending a message.
2. **No patient install.** Every patient touchpoint is a link, a message or the web portal (v1.1, C1).
3. **Three taps for the doctor.** Any doctor action that needs training is a design defect.
4. **Predictable price.** One MediEase invoice: the flat subscription plus the clinic's WhatsApp
   usage at cost plus a stated markup (v1.1, C5); nothing else per message or per patient.
5. **The clinic owns its patients.** Discovery lists a clinic and sends it requests; the patient
   relationship, records and communication stay with the clinic. No commission, ads or paid ranking.
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
| 6 | Clinic-owned booking / query landing page | P0 (v1.2) | FR-PUB | B4–B7 |
| 7 | Vaccination schedule tracking and due-date alerts | P1 | FR-VAX | A3 |
| 8 | Broadcast announcements to patient groups | P1 | FR-BRD | A1 |
| 9 | Advanced patient search and filters | P1 | FR-PAT-07 | A11, A12 |
| 10 | Specialty templates (Dental, Gynaecology, Physiotherapy, Homoeopathy, Paediatrics) | P1 | FR-TPL | A13 |
| 11 | Clinic billing: fees, receipts, dues, daily collection (v1.2, C12) | P1 | FR-BIL-01..07 | — |
| 12 | Analytics: volume, follow-up compliance, no-show rate | P2 | FR-ANL | — |
| 13 | Role-specific workspaces: Owner, Doctor, Front Desk (C10) | P0 | FR-UX | A13 |
| 14 | Patient account (Google), fresh dashboard, multi-clinic appointments (C9) | P0 | FR-PRT | Owner direction |
| 15 | Booking requests accepted/declined by front desk (C7) | P0 | FR-BKG | B4–B7 |
| 16 | Clinic and doctor discovery by name, clinic, speciality (C7) | P0 | FR-DIS | Owner direction |
| 17 | Verified clinic onboarding, approval and status (C8) | P0 | FR-ONB | Owner direction |
| 18 | Notification service: in-app, WhatsApp, later email/SMS (C11) | P0 | FR-NTF-02..06 | — |
| 19 | Landing page and plan limits (C14) | P0 / P1 | FR-LND, FR-SUB | Owner direction |
| 20 | Clinic stock inventory (C13) | P1 | FR-INV | Owner direction |
| 21 | Medical-store workspace (C13) | P2 | FR-PHA | Owner direction |
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
| FR-ORG-03 | A clinic has **Staff users** with exactly one role per clinic: `OWNER`, `DOCTOR`, `FRONT_DESK`. **v1.2:** a practising owner is an `OWNER` membership with a **linked doctor profile**, which grants doctor permissions (clinical write) without a second role. Such an owner has an **Owner / Doctor workspace switch**, and the Doctor view (my queue, *My Patients*, consultation and prescriptions) works for them exactly as for a `DOCTOR` (FR-UX-06). Clinic setup can mark the owner as **Doctor 1 in the same onboarding step** (FR-ONB-08). | P0 |
| FR-ORG-04 | The owner can invite, deactivate and change the role of staff. Deactivation takes effect on the next request. | P0 |
| FR-AUTH-01 | Staff sign in with phone number or email + password. Passwords are hashed with Argon2id. | P0 |
| FR-AUTH-02 | Sessions use short-lived access tokens and rotating refresh tokens in `HttpOnly`, `Secure`, `SameSite=Lax` cookies. | P0 |
| FR-AUTH-03 | Every API request is authorised against role **and** clinic membership; cross-clinic access is impossible by construction (see ADR-0003). | P0 |
| FR-AUTH-04 | Sign-in is rate-limited and locks for 15 minutes after 5 consecutive failures. | P0 |
| FR-AUTH-05 | Password reset for staff and patients. **v1.2:** by a single-use, time-limited link sent by email (FR-AUTH-08), not through the messaging port. | P0 (v1.2) |
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
| Accept / decline / propose-another-slot on booking requests | ✅ | ✅ (own patients, optional) | ✅ | — |
| Create billing entries and receipts | ✅ | ✅ (own consultations) | ✅ | — |
| Edit fee schedule, publish clinic/doctor public profile | ✅ | — | — | — |
| Manage stock (FR-INV) | ✅ | view only | ✅ | — |
| Review / approve / reject / suspend clinic applications | — | — | — | ✅ (`OPS_REVIEWER`) |

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

### 8.9 Public booking page — `FR-PUB` (P0 from v1.2; see also FR-DIS and FR-BKG in §8.14)

| ID | Requirement | Priority |
|---|---|---|
| FR-PUB-01 | Each clinic that is `ACTIVE` and verified gets a public page at `/c/{clinic-slug}` with name, address, map link, hours, doctors and a booking/query form. It works whether or not the clinic is listed in the directory (FR-DIS-07). | P0 |
| FR-PUB-02 | The form creates a **booking request** (FR-BKG) that front desk accepts or declines; it does not auto-book in MVP. | P0 |
| FR-PUB-03 | **v1.2:** no SMS OTP (cost). A booking request requires a **verified identity**: a signed-in patient account (Google, or email and password with a verified email, FR-AUTH-08); rate-limited per account, phone and IP. | P0 |
| FR-PUB-04 | The page link is shareable to WhatsApp status and Google Business Profile. | P0 |

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

### 8.14 v1.2 additions — `FR-ONB`, `FR-DIS`, `FR-BKG`, `FR-UX`, `FR-NTF`, `FR-BIL`, `FR-INV`, `FR-PHA`, `FR-SUB`, `FR-LND`

Detailed behaviour is specified per phase in `docs/specs/`. Priorities below say what is needed for the
M6 demo and pilot (P0), shortly after (P1), and later (P2).

#### Verified clinic onboarding — `FR-ONB` (C8)

Three things are modelled separately and never inferred from each other:

| Concept | Where it lives | Values | Who changes it |
|---|---|---|---|
| **Application status** | A clinic application (platform data, not tenant data) | `PENDING → UNDER_REVIEW → APPROVED \| REJECTED` | MediEase reviewer |
| **Clinic operational status** | The clinic (unchanged since M1) | `ONBOARDING → ACTIVE ↔ SUSPENDED` | Onboarding completion; ops (suspend) |
| **Verification** | The clinic and each doctor: verified by whom, when, against which application or check | verified / not verified | MediEase reviewer only |
| **Listing** | The clinic and each doctor: the owner's "Listed in MediEase directory" / "visible" switch | listed / not listed | Owner, only once allowed (FR-ONB-10) |

`Clinic.status` never says whether a clinic applied or passed MediEase verification.

| ID | Requirement | Priority |
|---|---|---|
| FR-ONB-01 | **Self-service application.** A public form lets a clinic or a solo doctor apply. It collects: clinic name, address, city/PIN, owner name, phone and **verified email**, specialties, each doctor's name, qualification, council and registration number, an upload of the registration certificate, and whether the owner is also a practising doctor. Submitting creates an application in `PENDING`; the applicant gets an email confirmation (FR-AUTH-08). | P0 |
| FR-ONB-02 | **Application lifecycle.** `PENDING → UNDER_REVIEW → APPROVED \| REJECTED`. It is a separate record from the clinic: no clinic, user or membership exists until approval. A clinic is **not discoverable** unless FR-ONB-09 holds, and **cannot receive booking requests** unless it is `ACTIVE` and verified. | P0 |
| FR-ONB-03 | **Manual verification by MediEase.** An `OPS_REVIEWER` sees a queue of applications, takes one (`UNDER_REVIEW`), checks each doctor's registration number against the state medical council register and the uploaded certificate, records the result per doctor, and decides with a reason. Every transition records reviewer, time and reason, and is audited (FR-AUD-01). Reviewers never see clinical content. | P0 |
| FR-ONB-04 | **Approved clinic onboarding.** Approval creates the clinic in `ONBOARDING`, records it and the checked doctors as verified, and sends the owner an invitation to finish onboarding (checklist, FR-OPS-04) and to invite doctors and front-desk staff through the existing invitation model. The clinic becomes `ACTIVE` when the checklist is complete. Tenant isolation is unchanged. | P0 |
| FR-ONB-05 | A rejected applicant is told the reason and may re-apply. A suspended clinic disappears from discovery within 5 minutes and its pending booking requests are cancelled with patients notified. | P0 |
| FR-ONB-06 | Clinics created directly by the ops team (FR-OPS-01) start **unverified**; they become verified only after a reviewer records the same checks. | P0 |
| FR-ONB-07 | Applications are rate-limited per phone and IP, and duplicate applications (same registration number) are flagged to the reviewer. | P1 |
| FR-ONB-08 | **One creation path.** Approving an application **pre-fills the ops Create-clinic wizard** (FR-OPS-01) and sends the owner's invitation, so self-service and ops-created clinics are created by the same code. The wizard can mark the owner as **Doctor 1 in the same step**: accepting the invitation links the owner's user to that doctor profile (FR-ORG-03). | P0 |
| FR-ONB-09 | **Discoverable = `ACTIVE` ∧ verified ∧ listed.** One domain rule decides it, and every public endpoint (search, profiles, slots) uses that rule. A doctor is shown only if verified **and** marked visible, in a discoverable clinic. Approval alone never makes a clinic public. | P0 |
| FR-ONB-10 | **Listing requirements.** The owner can switch listing on only when the clinic is `ACTIVE`, verified and its public profile is complete: onboarding checklist done, address and city/PIN, opening hours, and at least one verified, visible doctor with a schedule. If the clinic is suspended or the profile becomes incomplete, it leaves discovery at once and the owner sees why. | P0 |

#### Discovery — `FR-DIS` (C7)

| ID | Requirement | Priority |
|---|---|---|
| FR-DIS-01 | The directory lists only **discoverable** clinics and doctors (FR-ONB-09). | P0 |
| FR-DIS-02 | **Clinic search** by clinic name, speciality and city/PIN, and **doctor search** by doctor name, speciality, clinic and city/PIN, filtered by language and "has availability in the next 7 days". Results return in < 500 ms at pilot scale. | P0 |
| FR-DIS-03 | A public **clinic profile** and **doctor profile** show only what the clinic chose to publish: name, address, map link, hours, specialties, doctors, qualifications, consultation fee (optional), languages. No patient data, no clinical content. | P0 |
| FR-DIS-04 | Results are ordered by relevance, then distance and availability. **No paid ranking, sponsored listings, ads or ratings/reviews** in MVP. | P0 |
| FR-DIS-05 | Slots a patient sees are generated from the doctor's schedule and exceptions (FR-APT-01), minus booked slots and held requests. Clinics in token mode show sessions instead of times. | P0 |
| FR-DIS-06 | Public profile pages are indexable by search engines unless the clinic opts out; they load in < 2 s on 3G. | P1 |
| FR-DIS-07 | The clinic can still use its own link `/c/{clinic-slug}` (FR-PUB-01) without being listed in the directory. | P0 |
| FR-DIS-08 | **Discovery to booking.** From a clinic or doctor profile the patient picks a slot (FR-DIS-05); if not signed in, they sign in or sign up and return to the same slot; the request then follows FR-BKG and lands in that clinic's front-desk inbox. A profile of a clinic that is no longer discoverable answers exactly like "not found" (NFR-19). | P0 |

#### Patient account and booking requests — `FR-PRT` (amended), `FR-BKG` (C7, C9)

| ID | Requirement | Priority |
|---|---|---|
| FR-PRT-05 | **Google OAuth sign-up** (or email and password) creates a global patient account. First sign-in shows a **fresh dashboard**: 0 upcoming appointments, no prescriptions, no notifications, one primary action *Find a doctor*. No data is imported or inferred. | P0 |
| FR-PRT-06 | **Amends FR-PRT-02.** A patient account is linked to a clinic's patient record when (a) the clinic **accepts a booking request** and front desk selects or creates the matching patient record, (b) a single-use clinic invite is used, or (c) a prescription link passes its last-4-digit check. Linking never happens automatically by phone number alone (family members may share a phone, FR-PAT-02). | P0 |
| FR-PRT-07 | **My Appointments** is grouped by clinic, each showing doctor, date/time and status (`Requested`, `Confirmed`, `Declined`, `Cancelled`, `Completed`). Records of one clinic are never shown inside another clinic's group. | P0 |
| FR-PRT-08 | A patient can cancel a request or confirmed appointment, and request a reschedule, subject to a clinic-set cut-off (default 2 hours before). | P1 |
| FR-PRT-09 | A patient can book for themselves or for a dependent (child, parent) on the same account. | P1 |
| FR-PRT-10 | Data rights from the portal: download my account data, change consent and language per clinic, delete my account. Clinic medical records are retained as the clinic is legally required (§10). | P1 |
| FR-BKG-01 | A booking request captures doctor, slot (or session), patient, a short reason (free text, with a visible "not for emergencies" notice) and contact phone (from the verified patient account). | P0 |
| FR-BKG-02 | Creating a request places a **soft hold** on the slot (default 2 hours, clinic-configurable) so two patients cannot request the same slot, consistent with FR-APT-04. | P0 |
| FR-BKG-03 | The request raises a **BookingRequested** event; the front desk gets an in-app notification (and WhatsApp when enabled). | P0 |
| FR-BKG-04 | Front desk can **accept**, **decline (with reason)** or **propose another slot**. Doctors and owners can do the same. | P0 |
| FR-BKG-05 | **Accept** creates the appointment (source `PUBLIC_PAGE` or `PORTAL`, FR-APT-07), links the account (FR-PRT-06) and notifies the patient. **Decline** releases the hold and notifies the patient. | P0 |
| FR-BKG-06 | If nobody responds within the clinic's response window (default 4 hours, or 1 hour before the slot), the request **expires**, the hold is released, the patient is told, and front desk sees an "expired" count. | P0 |
| FR-BKG-07 | Abuse controls: verified identity before any request (FR-PUB-03), rate limits per account, phone and IP, a cap of 5 open requests per patient, and a no-show counter visible to staff. Staff decide; there is no automatic ban. | P0 |
| FR-BKG-08 | A doctor or front desk can book on behalf of a patient at any time (FR-APT-03); this is separate from patient requests and is not subject to FR-BKG-06. | P0 |

#### Role-specific workspaces — `FR-UX` (C10)

| ID | Requirement | Priority |
|---|---|---|
| FR-UX-01 | **Owner** home: clinic overview, today's volume, revenue and dues, staff and doctors, booking-request response rate, public profile status, settings, reports, integrations. | P0 |
| FR-UX-02 | **Doctor** home: *my* appointments today and queue, my patients, patient history, consultation and prescription, follow-ups due, my schedule and leave, notifications. | P0 |
| FR-UX-03 | **Front Desk** home: today's queue and calendar, **booking-requests inbox** (accept / decline / propose), register and search patients, walk-ins, reschedule/cancel, payments and receipts, patient communication. | P0 |
| FR-UX-04 | Each role has its own navigation and default landing screen; items a role may not use are **not shown**, not just disabled. A front-desk user never sees clinical notes (§8.1). | P0 |
| FR-UX-05 | Acceptance: sign in as each role on a 1366×768 desktop; the home screen, navigation and first three actions differ, and a Playwright test asserts it. | P0 |
| FR-UX-06 | **Practising owner.** An owner with a linked doctor profile (FR-ORG-03) gets an **Owner / Doctor switch** in the shell. The Doctor view is the same workspace a `DOCTOR` gets, scoped to the owner's own doctor profile: my queue and *Today*, **My Patients**, patient history, consultation and prescriptions, my follow-ups and schedule. The switch changes the view only, never the permissions; an owner without a doctor profile sees no switch. Acceptance: a Playwright test signs in as a practising owner, switches to Doctor and sees only their own patients and sessions. | P0 |

#### Notifications — `FR-NTF` (C11)

| ID | Requirement | Priority |
|---|---|---|
| FR-NTF-02 | Features publish **domain events** (e.g. `BookingRequested`, `AppointmentConfirmed`); a notification service maps each event to recipients and channels. No feature calls WhatsApp directly. | P0 |
| FR-NTF-03 | Channels: `IN_APP` (P0), `WHATSAPP` via the messaging port (P0, per-clinic number in M8), `EMAIL` and `SMS` (P2). Each recipient has per-channel preferences. | P0 |
| FR-NTF-04 | Event catalogue (MVP): booking requested / accepted / declined / expired, appointment confirmed / moved / cancelled, appointment reminder, follow-up due, prescription ready, medicine due, message failed, clinic application decided, subscription notices. | P0 |
| FR-NTF-05 | A notification centre for patients and for each staff role: unread badge, read state, deep link to the item. In-app delivery ignores quiet hours; WhatsApp/SMS obey FR-REM-04. | P0 |
| FR-NTF-06 | Delivery is at-least-once and idempotent (NFR-13). Notification text never contains diagnosis or medicine names (FR-MSG-04). | P0 |

#### Clinic billing — `FR-BIL-01..07` (C12)

| ID | Requirement | Priority |
|---|---|---|
| FR-BIL-01 | Per-doctor and per-service **fee schedule** (consultation, follow-up, procedure). | P1 |
| FR-BIL-02 | A bill is created from a visit or walk-in with line items, discount (amount or %) and notes. | P1 |
| FR-BIL-03 | Payment is **recorded** as cash, UPI or card (no gateway in MVP); partial payments allowed. | P1 |
| FR-BIL-04 | A receipt PDF with clinic letterhead; sent to the patient by link. | P1 |
| FR-BIL-05 | **Outstanding dues** per patient and a clinic-wide dues list. | P1 |
| FR-BIL-06 | **Daily collection** report by payment mode and by doctor; export CSV. | P1 |
| FR-BIL-07 | Bills are immutable once issued; corrections create a credit note. Edits are audited. | P1 |

#### Inventory and medical stores — `FR-INV`, `FR-PHA` (C13)

| ID | Requirement | Priority |
|---|---|---|
| FR-INV-01 | Clinic stock items with batch, expiry, quantity, unit price and supplier; stock-in and manual adjustment (audited). | P1 |
| FR-INV-02 | Dispensing can be linked to a prescription line; stock decrements. MediEase never suggests a medicine or substitute (FR-RX-10). | P1 |
| FR-INV-03 | Low-stock and near-expiry alerts to owner and front desk. | P1 |
| FR-PHA-01 | A **medical-store** tenant (new role `PHARMACIST`) with its own staff, stock and billing, separate from any clinic. | P2 |
| FR-PHA-02 | A patient can share a prescription with a store by **time-limited code**. The store sees only the medicine lines and patient name, **not diagnosis, visit notes or history**, and marks lines as dispensed. | P2 |
| FR-PHA-03 | Counsel to confirm drug-licence and prescription-handling obligations before FR-PHA ships (§10). | P2 |

#### Subscription and landing page — `FR-SUB`, `FR-LND` (C14)

| ID | Requirement | Priority |
|---|---|---|
| FR-SUB-01 | Plans by clinic size (§12) with limits on doctors and users enforced by the tenancy layer; a 14-day trial with no card. | P1 |
| FR-SUB-02 | Lifecycle: trial → active → payment overdue (7-day grace, read-only banner) → suspended. Suspended clinics are removed from discovery; data is retained for 30 days and exportable by the owner. | P1 |
| FR-SUB-03 | The owner can export all clinic data (patients, visits metadata, bills) as CSV at any time. | P1 |
| FR-LND-01 | A public landing page with a clinic path (benefits, features, pricing, **Apply to join MediEase**, book a demo) and a patient path (**Find a doctor**, Sign in with Google). | P0 |
| FR-LND-02 | Content: problem, 5-minute onboarding promise, role-based screenshots, pricing tiers, security and privacy summary, FAQ; English and Hindi. No clinical claims. | P0 |
| FR-LND-03 | LCP < 2.5 s on 4G, WCAG 2.1 AA, indexable, analytics events without PII (§11.3). | P0 |

#### Other gaps closed

| ID | Requirement | Priority |
|---|---|---|
| FR-PAT-09 | **Merge** two patient records in a clinic, with preview, undo window and audit (FR-AUD-01 already refers to merges). | P1 |
| FR-AUTH-08 | **Email provider** (free-tier transactional service): verify email addresses, password reset (FR-AUTH-05), application and invitation emails, and the later `EMAIL` notification channel. Password sign-ups cannot request a booking until the email is verified; Google accounts are already verified. | P0 |
| FR-ORG-07 | The owner has a web **Team page** to invite staff, change roles and deactivate (API already exists, FR-ORG-04). | P0 |
| FR-APT-09 | When a doctor adds leave over dates that already have appointments, front desk sees the affected list and can reschedule or cancel each, and patients are notified. | P0 |
| FR-APT-08 | (existing) Appointment reminders: scheduled for M6a. | P0 |
| FR-QUE-06 | (existing) Live token status link: scheduled for M6b. | P1 |
| FR-VIS-04 | (existing) Report attachments and patient-visible documents where the clinic allows: scheduled for M6d. | P1 |

### 8.15 v1.3 additions — `FR-AI-04`, `FR-RX-11`, `FR-UPL` (C15, C16)

Specs: `docs/specs/assistant.md` (M7a) and `docs/specs/prescription-uploads.md` (M7b); ADR-0023,
ADR-0024.

| ID | Requirement | Priority |
|---|---|---|
| FR-AI-04 | **Prescription explanation from the record.** The assistant explains only a prescription the user explicitly chose (the portal picker, or a verified upload, FR-UPL-04) and only by restating that version's database record in plain words: what was prescribed, when, how much, how long, and the doctor's own advice. It never reads an uploaded file's content, never fills a gap, and never changes or adds an instruction. | P0 for FR-AI |
| FR-RX-11 | **Printed verification code.** Every prescription version issued from M7 prints, in a fixed block outside the clinic's content and on every page, the MediEase mark, its own ID as a human-readable *verification code* and a QR code holding only `MEDIEASE-RX:1:<id>`. No personal or clinical data is encoded. Versions issued earlier keep their layout. | P0 |
| FR-UPL-01 | A signed-in patient account can upload a photo (JPEG, PNG) or PDF of a MediEase prescription, at most 10 MB, or type its verification code. Files are recognised by their bytes, held in quarantine and never shown to clinic staff. | P1 |
| FR-UPL-02 | Every uploaded file is scanned for malware (ClamAV) before anything reads it; an infected file, or one that cannot be scanned after retries, is rejected and deleted. | P0 for FR-UPL |
| FR-UPL-03 | Only the MediEase identifier is read from a clean file: the QR code, else the PDF's text layer. No OCR; when nothing is found the user is asked to retake the photo or type the code. Nothing else read from a file is kept or used. | P1 |
| FR-UPL-04 | **Verification against the database and the uploader's access.** The identifier must name an issued (or superseded) MediEase version that is either one of the account's own linked records, or, for a family member or representative, passes that prescription's last-4-digit check from a verified account, which grants access to that one prescription only, for 24 hours, never to the patient's record. A superseded version is shown as historical and the user chooses it or the latest explicitly; nothing is substituted silently. | P0 for FR-UPL |
| FR-UPL-05 | Only a verified upload reaches the assistant, and only as the database record (FR-AI-04). The file is deleted once identified or rejected; abandoned uploads are rejected and deleted after an hour; upload rows are deleted 30 days after their outcome. | P0 for FR-UPL |

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
| NFR-17 | Privacy | Public discovery and profile endpoints return only fields the clinic published; automated tests prove no patient, clinical or staff-private data can appear there. |
| NFR-18 | Multi-tenancy | A global patient account never gives access to a clinic's data except through a link created under FR-PRT-06; tests prove an account cannot read a clinic it is not linked to. |
| NFR-19 | Abuse | Public endpoints (application, search, booking request) are rate-limited and require a verified identity where a patient or applicant acts; response for a clinic that is not discoverable (directory and profiles), or not `ACTIVE` and verified (own link and booking requests), is identical to "not found". |
| NFR-20 | Upload safety | Uploaded files are untrusted: type allow-list by content, 10 MB, page and pixel caps before decoding, a malware scan before any parsing, processing on a separate worker so reminders are never delayed, no upload content in logs, audit metadata or any model, deletion after the outcome, and rate limits per account and caller. |

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
- **v1.2: MediEase's role grows.** A global patient account and a public directory mean MediEase decides
  how that account data and listing content are used, so MediEase is likely a *Data Fiduciary* for those,
  while each clinic stays the fiduciary for its clinical records. Counsel must confirm and the privacy
  notice must say so before the directory launches.
- **v1.2: Doctor listings.** Indian rules on how doctors may advertise or solicit patients apply to a
  directory. MVP therefore shows factual profile data only, with no ratings, no paid ranking and no
  claims; counsel reviews the wording before launch.
- **v1.2: Dispensing.** Inventory and the medical-store workspace touch drug-licence and
  prescription-handling rules. They are P1/P2 and need counsel review before they ship.

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
| Paid conversion | 2 clinics on a paid plan within 30 days | billing ledger |
| Booking requests answered within the response window | ≥ 90% | booking-request events |
| Median time to accept/decline a request | < 30 min in clinic hours | booking-request events |
| Clinic applications reviewed | < 2 business days | onboarding events |
| Requests that become attended visits | Baseline in month 1 | appointments, visits |

### 11.3 Product analytics events (no PII, no clinical content)

`clinic_onboarding_step_completed`, `appointment_created`, `queue_status_changed`,
`visit_completed`, `prescription_issued`, `prescription_link_opened`, `reminder_scheduled`,
`message_status_changed`, `patient_opted_out`, `public_booking_requested`,
`booking_request_created`, `booking_request_accepted`, `booking_request_declined`,
`booking_request_expired`, `clinic_application_submitted`, `clinic_application_decided`,
`patient_account_created`, `directory_search_performed`.
Properties are limited to IDs, enums, counts and durations.

## 12. Pricing and packaging (hypothesis to test)

Priced by clinic size and deliberately below the competitors in §5. **All figures are hypotheses to
test, not decisions; the developer to confirm before the landing page publishes prices.**

| Plan | Price (proposed) | Includes |
|---|---|---|
| Solo | ₹499 / month | 1 doctor + 1 staff user; appointments, queue, records, prescriptions, billing, directory listing |
| Clinic | ₹999 / month | Up to 3 doctors and 5 users; everything in Solo |
| Clinic Plus | ₹1,499 / month | Up to 5 doctors and unlimited staff; everything in Clinic, inventory when shipped |
| Medical store (later) | ₹499 / month | Store workspace and stock (FR-PHA) |
| Free trial | 14 days, no card | Full product; in-person onboarding for design partners |

- Directory listing and patient booking requests are **included**: no commission, no per-booking fee.
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
| **M6a Auth, staff workspaces and notification core** (v1.2; issue #49, branch `m6/49-mvp-demo`) | Design system (done); Google sign-in for staff and patients and patient email-and-password accounts kept apart from staff (ADR-0015); email provider with email verification and password reset; owner Team page; separate Owner, Doctor and Front Desk workspaces; practising owner's Owner / Doctor switch with *My Patients*, and the ops wizard marking the owner as Doctor 1; notification service with in-app channel behind a port; appointment reminders; doctor-leave conflicts; owner audit view | FR-AUTH-05, 07, 08, FR-PRT-01 (account only), FR-ORG-03, FR-ORG-07, FR-UX-01..06, FR-NTF-02..06, FR-APT-08, 09, FR-AUD-03 | Three roles, and a practising owner in both views, show different home screens and navigation (Playwright); a patient and a staff member each sign in with Google (fake provider) and stay apart; `make e2e` green |
| **M6b Patient identity, portal and booking requests** (v1.1/v1.2) | Linking an account to a clinic's record (invite, prescription link, accepted request); patient portal with the fresh dashboard and *Find a doctor* entry, My Appointments by clinic, prescriptions and reminders; medicine planner; per-clinic public page `/c/{slug}`; booking requests from a verified account with soft hold; front-desk inbox (accept / decline / propose / expire); patient notifications; live token link | FR-PRT-02..07, FR-BKG, FR-PUB, FR-REM-03, FR-QUE-06 | Patient requests on `/c/{slug}`, front desk accepts, appointment appears under the right clinic; cross-clinic isolation tests pass |
| **M6c SaaS clinic onboarding, verification and discovery** (v1.2) | (1) Self-service clinic and solo-doctor application; (2) application lifecycle `PENDING → UNDER_REVIEW → APPROVED \| REJECTED`, kept apart from clinic status; (3) MediEase reviewer workflow: queue, manual registration checks per doctor, decision with reason, audit; (4) approved clinic onboarding through the pre-filled Create-clinic wizard, owner as Doctor 1, owner invitation; (5) verification and listing modelled separately, with listing requirements; (6) public clinic and doctor profiles; (7) clinic search and doctor search with filters; (8) discovery-to-booking into the M6b request flow; (9) landing page v1 | FR-ONB-01..10, FR-DIS-01..08, FR-LND, NFR-17, NFR-19 | A pending, approved-but-unlisted or suspended clinic is invisible in discovery; an `ACTIVE`, verified and listed clinic is found by clinic and by doctor search and requested within one session |
| **M6d Billing and documents** (v1.2) | Fee schedule, bills, receipts, dues, daily collection, report attachments, plan limits and trial | FR-BIL-01..07, FR-VIS-04, FR-SUB-01 | Daily collection matches recorded payments; plan limits enforced |
| **M7a AI assistant** (v1.3, C15; issue #65) | LLM gateway (Groq first, console adapter), patient and staff assistants with tools under the caller's permissions, signed confirmations, guard rails, prescription explanation from the record, layout 3 with the verification code | FR-AI-01..04, FR-RX-11 | Booking by chat with a confirmation, the guard-rail tests and the provider switch by settings pass; new prescriptions print a code and QR that decode to their ID |
| **M7b Verified prescription uploads** (v1.3, C16; issue #65, same branch and PR) | Upload and quarantine, ClamAV on a separate worker, identifier extraction (no OCR), verification for own records and representatives, superseded choice, handoff to the assistant, deletion | FR-UPL-01..05, NFR-20 | An edited upload with a genuine QR is explained only from the record; EICAR is rejected and deleted; another account's prescription is refused without the last-4 proof |
| **M8 Multi-clinic WhatsApp and consolidated billing** (v1.1) | Embedded Signup per clinic, per-clinic templates and webhooks, usage ledger, one MediEase invoice | FR-BIL-WA | Two clinics' usage billed separately with no mixing |
| **M9 Pilot hardening** | Backups, monitoring, ops health view, security review, deploy | NFR-03..07, FR-OPS-03 | Restore drill done; security checklist signed |
| **— Pilot launch —** | Two clinics live | G1–G5 | Scorecard §11.2 tracked weekly |
| **M10+** | Clinic inventory (FR-INV), vaccination, broadcasts, specialty templates, search, analytics, patient merge, subscription lifecycle and data export, then medical-store workspace (FR-PHA), email/SMS channels | FR-INV, FR-VAX, FR-BRD, FR-TPL, FR-PAT-07, 09, FR-ANL, FR-SUB-02, 03, FR-PHA | Driven by pilot feedback; FR-PHA only after counsel review |

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
| Directory has too few clinics to attract patients (cold start) | High | Clinics keep their own link and queue regardless; open the directory by city only once several clinics are active; discovery is never the reason a clinic pays |
| Fake or unqualified clinic or doctor listed | Severe | Manual verification of registration numbers (FR-ONB-03), suspend-in-5-minutes (FR-ONB-05), audit of every decision |
| Front desk ignores booking requests, so patients lose trust | High | Expiry with patient notice (FR-BKG-06), response-rate on owner dashboard, reminders to the desk |
| Doctor-advertising and data-fiduciary rules apply to a directory | High | Facts-only profiles, no ratings or paid ranking, counsel review before launch (§10) |
| Scope creep: SaaS + discovery + billing + inventory + stores for a small team | High | Strict M6a–d order; P2 items (FR-PHA, email/SMS) wait for pilot evidence; each sub-milestone has its own exit test |
| Aggressive pricing cannot cover WhatsApp and infrastructure cost | Medium | Track cost per clinic (NFR-16, FR-MSG-07); WhatsApp usage billed at cost plus markup (C5) |

### 14.2 Assumptions

- A1: Patients will open a link sent on WhatsApp without installing anything.
- A2: One shared MediEase WhatsApp number with clinic-named templates is acceptable to clinics at MVP.
- A3: Pilot clinics have at least one desktop or laptop at the front desk and a smartphone for the doctor.
- A4: English staff UI is acceptable for pilot clinics; Hindi is needed for patients.
- A5: The pilot runs on a single-region deployment in India.
- A6: Patients will use Google sign-in and request a booking rather than phoning the clinic.
- A7: Small clinics are willing to be listed publicly and to answer requests within a few hours.
- A8: A clinic's registration certificate and council number are enough for a manual verification decision.

### 14.3 Open questions

1. Will clinics accept a patient surface that is only WhatsApp + web link?
2. In multi-doctor practices, who authorises a recurring payment — doctor or owner?
3. Does prescription clarity drive adoption on its own, or only once booking and records are in place?
4. How many "manual is fine" businesses reverse on a second conversation (as A5 → B6 did)?
5. Token mode vs time slots — which do pilot clinics actually run? (Built both; measure.)
6. Is a clinic-owned WhatsApp number a buying criterion? (Currently P2.)
7. When should ABDM/ABHA integration enter the roadmap?
8. What exactly does "approved" promise patients: identity of the doctor, or also quality? (MVP: identity only.)
9. Is directory listing free forever, or a paid add-on later? (MVP: free, included.)
10. Do pilot clinics want to be discoverable at all, or only to receive bookings on their own link?
11. How should a medical store receive a prescription without seeing more than it needs? (FR-PHA-02, needs counsel.)
12. Which front-desk response window do clinics actually keep? (FR-BKG-06 default is a guess.)

## 15. Glossary

See [GLOSSARY.md](GLOSSARY.md). Key terms: *Clinic* (tenant), *Session* (a doctor's block of
consultation time), *Token* (queue number within a session), *Visit* (one consultation),
*Prescription* (issued, immutable Rx document), *Patient link* (signed, expiring URL),
*Reminder* (scheduled outbound message), *Template* (Meta-approved WhatsApp message format).

## 16. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 15 Sep 2026 | First complete PRD from Phase 1 validation and Phase 2 readiness work |
| 1.1 | 20 Oct 2026 | C1–C6: patient portal, Google staff sign-in, medicine planner and notifications, AI assistant, consolidated WhatsApp invoice |
| 1.2 | 22 Oct 2026 | C7–C14: patient discovery and booking requests, verified clinic onboarding, Google patient accounts, role-specific workspaces, notification service, clinic billing, inventory and medical stores, SaaS packaging and landing page; M6 split into M6a–d; unscheduled FRs scheduled; pricing re-tiered (proposed); no SMS OTP (FR-PUB-03), email provider (FR-AUTH-08), practising owner as `OWNER` + linked doctor profile with an Owner / Doctor switch (FR-ORG-03, FR-UX-06), owner Team page (FR-ORG-07), application status, clinic status, verification and listing kept separate (FR-ONB-01..10), discovery-to-booking (FR-DIS-08) |
