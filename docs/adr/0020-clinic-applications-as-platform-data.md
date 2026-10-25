# ADR-0020: Clinic applications are platform data, and the applicant has no account until approval

| Field | Value |
|---|---|
| Status | Accepted (approved with M6c by the developer, 26 Oct 2026) |
| Date | 2026-10-26 |
| Deciders | Developer |
| Related | FR-ONB-01, 02, 04, 08; NFR-19; ADR-0003 (multi-tenancy), ADR-0016 (email) |

## Context

M6c lets a clinic or a solo doctor apply on the website. The PRD keeps four things apart: the
application's status (`PENDING → UNDER_REVIEW → APPROVED | REJECTED`), the clinic's operational
status (`ONBOARDING → ACTIVE ↔ SUSPENDED`), verification and listing; and FR-ONB-02 says no
clinic, user or membership exists until approval. Every tenant table carries `clinic_id`
(ADR-0003), and today the only identities are staff users and patient accounts. An application
needs a verified email (FR-ONB-01), holds personal data (owner contact, registration numbers) and
certificates, and must be readable by MediEase reviewers but by no clinic.

## Decision

Applications live in **platform tables** (`clinic_applications`, `clinic_application_doctors`),
outside any tenant, reached only through reviewed platform repositories from the public
application routes and the ops routes. The applicant has **no account**: the application holds the
owner's contact details, and the email is verified by a single-use link (a 256-bit secret, digest
stored) belonging to the application itself. Approval (M6c-P3) creates the clinic, its doctors and
the owner's staff user through the existing creation path and invitation, so the owner's first
credential is set when they accept it. Audit events for applications have no clinic and a new
actor type, `APPLICANT`.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| A clinic row in a new `APPLIED` status | One table; tenancy for free | `Clinic.status` would say whether a clinic applied, which the PRD forbids; rejected applicants would leave clinics behind | FR-ONB-02 |
| A staff user created at submission | Reuses `email_tokens` and sign-in | A user with no clinic, created by anyone on the internet; the invite model would have to accept pre-existing applicant users | FR-ONB-02; attack surface |
| A patient account required to apply | Reuses Google sign-in and verified email | A patient identity is not a clinic owner; mixes two audiences and two cookie domains (ADR-0015) | Wrong identity |

## Consequences

- Positive: rejected or abandoned applications never touch clinic data; tenancy rules are
  unchanged; the creation path stays single (FR-ONB-08).
- Negative / costs: a second email-verification mechanism next to `email_tokens`; platform
  repositories that must be reviewed like the other cross-clinic exceptions; personal data and
  certificates with their own retention (72 hours unverified, 180 days rejected, while the clinic
  exists when approved).
- Follow-ups: P2 adds reviewer columns and the per-doctor checks; P3 links an approved
  application to the clinic it created. Revisit if applicants need to edit an application after
  submitting (an applicant session would then be needed).
