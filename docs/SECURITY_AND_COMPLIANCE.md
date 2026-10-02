# MediEase — Security and Compliance

> This document records the engineering controls MediEase implements and how they map to the
> obligations we expect to face. It is **not legal advice**. Every item marked *Counsel* must be
> confirmed with a qualified lawyer before the pilot (TASKS.md L-04).

## 1. Legal and regulatory context (India)

| Framework | What it means for MediEase | Status |
|---|---|---|
| Digital Personal Data Protection Act, 2023 | Clinic = Data Fiduciary; MediEase = Data Processor acting under a contract | Design basis |
| DPDP Rules, 2025 (notified 14 Nov 2025, 18-month phased timeline) | Notice, consent, security safeguards, breach intimation, data principal requests, children's data. We build to the end-state now | Design basis; *Counsel* for exact dates and scope |
| Children's data under the Rules | Verifiable parental consent, with exemptions that include healthcare purposes | Guardian model built (FR-PAT-06); *Counsel* on applicability |
| Medical records retention for clinics | Clinics may be legally required to retain records for set periods | Erasure procedure respects retention; *Counsel* |
| Prescription content | Doctor's name, qualification and registration number on prescriptions | FR-ORG-02, FR-RX-06; *Counsel* on full format |
| WhatsApp Business Platform policies | Approved templates for business-initiated messages; opt-in; quality rating | FR-MSG-02, FR-MSG-05 |
| TRAI telecom commercial communication rules (DLT) | SMS sender IDs and templates registered on DLT | L-03 |
| ABDM (Ayushman Bharat Digital Mission) | Not integrated in MVP | Open question |

## 2. Data classification

| Class | Examples | Handling |
|---|---|---|
| **C3 Clinical** | Visit notes, diagnosis, vitals, prescription items, advice, attachments | Tenant-scoped; never in logs/messages/analytics; access audited; encrypted at rest |
| **C2 Personal** | Patient name, phone, DOB, guardian, staff contact details | Tenant-scoped; phones masked in logs; export/erasure supported |
| **C1 Operational** | IDs, statuses, timestamps, counts, error codes | May appear in logs and metrics |
| **S Secrets** | Passwords, tokens, keys, provider credentials | Environment/secret store only; never logged |

## 3. Controls checklist

Use this list in the M6 security review. Each row names where it is implemented.

### Identity and access
- [ ] Argon2id password hashing with per-hash salt (M1)
- [ ] Access token 15 min, refresh 14 days, rotation with reuse detection (M1)
- [ ] Cookies `HttpOnly`, `Secure` (non-local), `SameSite=Lax`; CSRF double-submit (M1)
- [ ] Lockout after 5 failed sign-ins; rate limit per IP and per account (M1)
- [ ] Role + membership check on every route; permission matrix tests (M1)
- [ ] Ops users cannot read clinical data; support access is owner-granted, time-boxed, audited (M1, P1 for grants)
- [ ] Deactivation effective on the next request (M1)

### Tenancy
- [ ] `clinic_id` on every tenant table; scoped repositories only (M1+)
- [ ] Permanent cross-tenant test suite covering every endpoint (M1+)
- [ ] Cross-tenant access returns 404 (M1+)
- [ ] PostgreSQL Row-Level Security as defence in depth (post-pilot, ADR-0003)

### Data protection
- [ ] TLS 1.2+ for all traffic; HSTS on the web origin (M6)
- [ ] Encryption at rest for database, backups and object storage (M6)
- [ ] Application-level encryption for `messages.to_phone_e164` (M5)
- [ ] Patient links: HMAC-signed, purpose-bound, 90-day expiry, revocable, last-4 challenge, attempt lockout, open audit (M4)
- [ ] PDFs via short-lived pre-signed URLs only (M4)
- [ ] India-region hosting for all data stores and backups (M6)
- [ ] No clinical content in message bodies — links only (M5)

### Application security
- [ ] Input validation with Pydantic at every boundary; output encoding in React (M0+)
- [ ] Parameterised SQL only (SQLAlchemy); no string-built queries (M0+)
- [ ] File uploads: type allow-list, size limit, stored outside web root, served via signed URL (P1)
- [x] Security headers: CSP, X-Content-Type-Options, Referrer-Policy, frame-ancestors none (M0-P4: nonce-based CSP per request in `apps/web/src/proxy.ts`, `script-src` without `'unsafe-inline'`; `Referrer-Policy: no-referrer`; `X-Frame-Options: DENY`; `Permissions-Policy`. HSTS joins with TLS in M6)
- [ ] Webhook signature verification on raw body; replay-safe processing (M5)
- [ ] Dependency and container image scanning in CI (M0-P5)
- [ ] Secrets scanning in CI (M0-P5)

### Audit and monitoring
- [ ] Append-only audit events for FR-AUD-01 actions, written in the same transaction (M1)
- [ ] Database role for the app cannot update/delete audit rows (M1)
- [ ] Alerts: 5xx rate, readiness, sign-in failure spikes, webhook signature failures, dead jobs (M6)
- [ ] Log review confirms no PII/clinical leakage (M6)

### Resilience
- [ ] Daily backups, PITR, 30-day retention, monthly restore drill (M6)
- [ ] Documented incident and breach procedures (RUNBOOK §15)

### Governance
- [ ] Data processing agreement template between clinic and MediEase (*Counsel*, L-04)
- [ ] Patient notice template clinics can display and share (*Counsel*, L-04)
- [ ] Sub-processor list (hosting, WhatsApp/Meta, SMS provider) shared with clinics (M6)
- [ ] Staff access reviews each quarter (post-pilot)

## 4. AI tooling rules

- AI agents work on synthetic data only; `.env` and secret files are denied in `.claude/settings.json`.
- No production data, logs containing identifiers, or screenshots of real records go into prompts.
- MediEase does not use AI to produce clinical content. Any future AI feature needs a PRD update,
  an ADR and a privacy review before design starts.
