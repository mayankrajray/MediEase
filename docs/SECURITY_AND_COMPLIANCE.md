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
| **C3 Clinical** | Visit notes, diagnosis, vitals, prescription items, advice, attachments; the patient's own dose marks (M6b-P3b, `dose_records`) | Tenant-scoped; never in logs/messages/analytics; access audited; encrypted at rest |
| **C2 Personal** | Patient name, phone, DOB, guardian, staff contact details | Tenant-scoped; phones masked in logs; export/erasure supported |
| **C1 Operational** | IDs, statuses, timestamps, counts, error codes | May appear in logs and metrics |
| **S Secrets** | Passwords, tokens, keys, provider credentials | Environment/secret store only; never logged |

## 3. Controls checklist

Use this list in the M6 security review. Each row names where it is implemented.

### Identity and access
- [x] Argon2id password hashing with per-hash salt (M1-P2: argon2-cffi, RFC 9106 low-memory profile t=3/64 MiB/p=4; hashes upgraded on sign-in when parameters rise)
- [x] Passwords are chosen, never issued: a staff invitation carries a single-use secret (32 random bytes, stored only as a SHA-256 digest, 7-day expiry, shown once) and the invitee sets a password of at least 12 characters (M1-P5). No password is ever transmitted to a new member, and the digest is useless to anyone who steals the database
- [x] Access token 15 min, refresh 14 days, rotation with reuse detection (M1-P2: HS256 JWT with pinned algorithm and required claims; refresh tokens stored as SHA-256; a rotated token revokes its family)
- [x] Cookies `HttpOnly`, `Secure` (non-local), `SameSite=Lax`; CSRF double-submit (M1-P2: path-scoped cookies; one hook guards every unsafe `/api/*` request with session cookies)
- [ ] Lockout after 5 failed sign-ins; rate limit per IP and per account (M1-P2: per-account lockout done, constant-time unknown-account path; per-IP rate limiting at the reverse proxy in M6-P1)
- [x] Role + membership check on every route; permission matrix tests (M1-P3: each route declares an access policy and one hook enforces it; `create_app` refuses to start if a route has none; the PRD §8.1 matrix is domain data with a table test, and the role × endpoint matrix is tested over HTTP)
- [ ] Ops users cannot read clinical data; support access is owner-granted, time-boxed, audited (M1-P3: ops accounts are refused on clinic routes and clinic staff on ops routes (R10); owner-granted support access is post-pilot, FR-OPS-05)
- [x] Browser session handling (M1-P6): no token is readable by scripts (`me_access`, `me_refresh` HttpOnly); the only script-readable cookie is `me_csrf`, which the API client copies into `X-CSRF-Token` on POST. A refresh is shared per tab and serialised across tabs with a Web Lock, so the single-use refresh token is not replayed by our own code. `?next=` only accepts same-site paths and `?reason=` only allow-listed values. The only thing in `localStorage` is `mediease.clinic_id`, a preference the API re-checks. The UI's redirects and hidden links are a convenience, never the control: the API enforces access on every request (the proxy's no-cookie redirect is a hint on `me_csrf` alone)
- [x] Invitation links cannot take over an existing account (found in M1-P6, fixed in the M1-P5 amendment, spec R13): accepting for an account that already has a password requires that account's current password and never changes it; wrong attempts share the sign-in lockout and are audited (`auth.sign_in_failed`, `via: invite`). Regression test: an owner who invites another clinic's user and accepts their own link gets 401 and the account is untouched
- [x] Patient sessions cannot reach staff routes, nor staff sessions patient routes (M6a-P3, ADR-0015): separate tables, cookies and JWT audiences; a permanent suite calls every staff route with a portal token (also copied into `me_access`) and every `@patient` route with a staff token, all 401. Google sign-in verifies the ID token's signature, `iss`, `aud`, `exp`, `nonce` and `email_verified`; `state` and the PKCE verifier live in a signed 10-minute HttpOnly cookie; it never creates staff access and refuses ops users; the fake provider is refused outside local and test. Sign-up, sign-in and Google are rate limited per caller. Accepted risk: sign-up reveals that an email has a password account (`PRT_EMAIL_TAKEN`, rate limited) until email verification exists (M6a-P4)
- [x] The owner's audit log (M6a-P8, FR-AUD-03): owners only (`AUDIT_VIEW`; doctors and the front desk get 403); read through one reader bound to the request's clinic, which filters every table it joins by that clinic (reviewed tenancy exception with its own cross-clinic case); IP fingerprints are never returned; the CSV export is bounded (92 days, 20,000 rows), prefixes any cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return with `'` (CSV injection), and is itself audited (`audit.exported`, FR-AUD-01 "data exports"); entries stay append-only (FR-AUD-02)
- [x] Password reset and email verification (M6a-P4, ADR-0016): a reset request answers the same 202 for any address and is rate limited per caller and silently per account; links are single-use, 30 minutes (reset) or 24 hours (verify), stored only as SHA-256 digests made by the worker at send time (never in a job payload), refused once superseded or if the account's email changed; a completed reset revokes every session and emails a notice; verification pages POST, so link scanners consume nothing; reset pages send no referrer; emails carry no clinical content and no tracking; logs carry masked addresses only. Not yet verified: real delivery and SPF/DKIM/DMARC (L-11); email addresses go to a processor outside India (Brevo) pending counsel (L-04)

- [x] Deactivation effective on the next request (M1-P3: the session, user status and membership are re-read on every request — no cached permissions; sign-out ends access at once)

### Tenancy
- [x] `clinic_id` on every tenant table; scoped repositories only (M1-P1: `TenantScopedRepository`, reachable only through `UnitOfWork.tenant(clinic_id)`; M1-P3: that ID comes from the request's resolved membership, never from the body)
- [ ] Permanent cross-tenant test suite covering every endpoint (M1-P1 repositories; M1-P3 adds the HTTP suite and a guard that fails when a clinic route taking a resource ID has no cross-clinic case; extended by every later milestone)
- [x] Cross-tenant access returns 404 (M1-P3: AC3 proved over HTTP; scoped repositories raise `NotFound`, logged as `tenancy.not_found`)
- [x] Dose records (M6b-P3b, R50–R54) are the patient's alone: no staff, ops or clinic route reads them (`tests/tenancy/test_dose_privacy.py` fails on any new reader), no audit row per mark, logs carry IDs and counts only (AC22's log-capture test), never sent to analytics or a model. Kept on unlink, shown again on a relink of the same record. Retention one year after the course ends (or the dose's day when open-ended) — **a product period subject to privacy and legal review (L-04), not a claimed DPDP requirement**. Export and deletion on request by support (`make dose-data`) until FR-PRT-10
- [x] The medicine plan and reminder choices (M6b-P3) stay in the account's scope: plan routes read through `PortalScope` (a cross-account case in the portal suite), choices are tenant rows deleted on unlink, reads and choices are not audited and logs carry IDs and counts only (a test checks no medicine or dose is logged). The plan only lays out the doctor's lines; it never computes a dose or adds an instruction (D9)
- [x] A patient account reads only the records linked to it (M6b-P1, NFR-18): every `@patient` read goes through `PortalScope` (the account's active links, per request), an ID outside it is 404, and `tests/tenancy/test_portal_scope.py` fails when a `@patient` route with an ID has no cross-account case. Links are made only from proof the clinic gave (an invite shown once, stored as a digest; or the prescription link's last-4 check from a verified account, with its lockout), never by matching a phone, email or name
- [x] Patient notifications (M6b-P6, R55-R68) belong to one account: written only for the request's account or the account linked to the record (never by phone, email or name), read through a reviewed cross-clinic lookup filtered by the portal scope (an unlinked or suspended clinic's appointment and prescription notices disappear), another account's ID is 404 (cross-account cases in the portal suite). They store IDs and codes only; titles, the booking emails and logs carry no diagnosis, medicine, reason text, staff note, phone or age (the decline email never names the reason)
- [ ] PostgreSQL Row-Level Security as defence in depth (post-pilot, ADR-0003)

### Data protection
- [ ] TLS 1.2+ for all traffic; HSTS on the web origin (M6)
- [ ] Encryption at rest for database, backups and object storage (M6)
- [x] Application-level encryption of the phone number on `messages` (`to_phone_encrypted`, Fernet keys in `MESSAGING_PHONE_KEYS`, M5-P2)
- [x] Patient links: HMAC-signed, purpose-bound, 90-day expiry, revocable, last-4 challenge, attempt lockout, open audit (M4-P5: HMAC-SHA256 tokens with versioned keys, the claims checked against the row; the last-4 check under a row lock with a five-attempt lockout only staff can reset; a 30-minute view token in an HttpOnly cookie scoped to the link's page; `patient_link.*` audit with IDs only; per-link and per-caller rate limits; no clinical content in the URL, title or logs; `noindex`, `no-store`, `no-referrer`)
- [x] The live token link (M6b-P6, ADR-0019, FR-QUE-06): public with **no last-4 check**, by decision, because it shows only the clinic, the doctor, a token or time, a count ahead and who is being seen (an allow-listed body; a test fails on any other key). HMAC-signed with the patient-link keys and bound to one appointment and one day (until 2 hours after the session); issued only for the account's own appointment (else 404) or by staff with `APPOINTMENTS_MANAGE`; `noindex`, `no-store`, `no-referrer`; 120 reads a minute per caller and 30 per link. It cannot be revoked before it expires (stateless): accepted for that content
- [x] Clinic applications (M6c-P1, ADR-0020, FR-ONB-01, 07, NFR-19): platform data with no clinic until approval; the applicant has no account; the owner's email is proved by a single-use link (256-bit secret, digest stored, minted at send time, 48 hours, a button press so mail scanners confirm nothing). Certificates: PDF, JPEG or PNG recognised by their first bytes (never parsed), at most 5 MB, private blobs under `applications/<id>/`, never a public URL, deleted with the application. Limits per address, owner phone and owner email; a honeypot answered like a success; duplicate registrations flagged for the reviewer, never revealed. Logs and audit carry IDs, kind and counts only (a test checks no name, phone, email, registration number or file name). Retention: unconfirmed 72 hours (hourly purge); rejected 180 days after the decision (the same purge); approved while the clinic exists
- [x] Reviewing applications and verification (M6c-P2, P3, FR-ONB-03..06, 08): ops roles `OPS_ADMIN` and `OPS_REVIEWER` (`users.ops_roles`; every earlier ops user holds both); only reviewers see an application's detail or certificate, each opening audited (`application.viewed`, `application.certificate_viewed`). A certificate is streamed through the session with its stored type, `inline`, `nosniff` and a `sandbox` CSP, never a public or pre-signed URL. Checks, rejection reasons and the reviewer's notes and messages are never in logs or audit metadata (a test reads the audit rows). Approval creates the clinic, doctors and the owner's emailed invitation in one transaction through the same rules as the ops wizard (FR-ONB-08). A clinic has a public page only when `ACTIVE` **and verified** (`has_public_page`); an ops-created clinic starts unverified; changing a doctor's registration clears its verification. Suspension (M6c-P4, `OPS_ADMIN`) removes every public surface at once and withdraws open requests in the same transaction; its reason code is audited, its free-text note is not. Listing is the owner's choice and needs verification (a database CHECK). Public profiles (M6c-P5) show only active, verified and shown doctors; the public body stays an allow-list (specialties, languages and an optional fee added); pages are indexable only when discoverable and not opted out, and `robots.txt` disallows signed-in areas, patient links and the API. Directory search (M6c-P6, ADR-0021) is a reviewed cross-clinic read of published columns returning IDs, every candidate re-checked by the discoverability rule; bound parameters only (no `LIKE` patterns from input); allow-list bodies; the public read rate limit; the searcher's words are never logged
- [ ] Per-patient IP rate limits on the public pages once the M6 proxy forwards the client address (today the API sees the web server)
- [x] PDFs only through the authenticated, audited API; no public or pre-signed URLs (M4-P4, ADR-0012: `GET /prescriptions/{id}/pdf` needs `RX_PRINT` and the caller's clinic, writes one `prescription.pdf_downloaded` per download, answers `Cache-Control: private, no-store`; files are rendered in-house by WeasyPrint with vendored fonts, the renderer fetches nothing and Jinja2 autoescapes every value, and the store is write-once with keys that cannot leave its root. Front desk may print an issued version but never reads one on screen, spec D6)
- [ ] Prescription PDFs encrypted at rest: the S3 adapter sets SSE (AES256) on every object; the local `blobs` volume relies on disk encryption (M6)
- [ ] India-region hosting for all data stores and backups (M6)
- [ ] No clinical content in message bodies — links only (M5; P2: template variables are typed to clinic name, doctor name, date/time/token, clinic phone and link, and the AC7 leakage test proves it for prescriptions)

### Application security
- [ ] Input validation with Pydantic at every boundary; output encoding in React (M0+)
- [ ] Parameterised SQL only (SQLAlchemy); no string-built queries (M0+)
- [ ] File uploads: type allow-list, size limit, stored outside web root, served via signed URL (P1)
- [x] Security headers: CSP, X-Content-Type-Options, Referrer-Policy, frame-ancestors none (M0-P4: nonce-based CSP per request in `apps/web/src/proxy.ts`, `script-src` without `'unsafe-inline'`; `Referrer-Policy: no-referrer`; `X-Frame-Options: DENY`; `Permissions-Policy`. HSTS joins with TLS in M6)
- [x] Webhook signature verification on raw body; replay-safe processing (M5-P3: HMAC-SHA256 over the raw bytes before parsing, constant-time; one row per body; forward-only statuses; stored bodies redacted to IDs and statuses)
- [x] Opt-out by reply without keeping inbound text (M5-P5, FR-MSG-05): a STOP reply is recognised before redaction and is the one inbound message that keeps anything about its sender — the number, Fernet-encrypted under `MESSAGING_PHONE_KEYS`, and the ID of our message it answered — only until its processing job runs (normally seconds; at worst the 7-day `webhook_events` purge). The cross-clinic opt-out lookup returns IDs only (a reviewed tenancy exception), each opt-out is a SYSTEM `patient.opted_out` audit event, and no log names the number
- [x] Public clinic page and booking requests (M6b-P4, NFR-17, NFR-19, FR-BKG-07): the unauthenticated body is an allow-list that a test fails on any extra key; an unknown slug and a clinic without a page are one 404; a request needs a verified account and the patient's not-an-emergency confirmation; limits per account, address and phone with `Retry-After`; the reason is clinical text and is never logged, audited or notified; the phone is masked in logs; staff booking over a patient's hold is an explicit, confirmed, audited action. The caller's address is the web server's until a trusted proxy sets it (ARCHITECTURE A11), so the per-address limits are shared in the pilot (RUNBOOK 24)
- [x] Dependency and container image scanning in CI (M0-P5: `pip-audit`, `npm audit --omit=dev --audit-level=high` blocking plus a full-tree `npm audit` that is informational only (exception: braces GHSA-vfj7-8cjw-p6xm has no patched version and is reachable only via dev-only `eslint-config-next`; revisit when patched or Next drops `fast-glob`), Trivy on both images failing on fixed HIGH/CRITICAL; Dependabot for pip, npm, Docker and Actions)
- [x] Fee schedule (M6d-P1, FR-BIL-01, spec billing R7, R9): `BILLING_MANAGE` (every role) reads it, `FEES_MANAGE` (owners) changes it, checked by the route policy and the permission matrix tests; tenant tables `clinic_services` and `doctor_service_prices` behind `TenantScopedRepository` with cross-clinic tests at the repository and HTTP levels; changes audited with IDs, kinds and amounts only (no names); prices bounded in the request, the domain and a database CHECK. Bills will copy no clinical content (B3, from P2)
- [x] Bills and credit notes (M6d-P2, FR-BIL-02, 07, ADR-0022, spec billing R21, R29, R30): snapshots with no clinical content (the visit gives only its patient and doctor); a doctor reaches only bills with their own profile (404 for another's); issued bills are immutable in the domain and by CHECKs, corrected only by numbered credit notes; tenant tables `bills` and `bill_lines` with cross-clinic tests; every change audited with IDs, numbers and amounts only
- [x] Payments and dues (M6d-P3, FR-BIL-03, 05, spec billing R31-R42): payments take the bill row lock and never exceed the balance; never edited or deleted, voided only the same clinic-local day with a reason; the dues list needs `COLLECTION_VIEW` (owners and the front desk, not doctors); the queue carries an amount only; tenant table `payments` with cross-clinic tests; every payment and void audited with IDs, kind, mode and amount
- [x] Secrets scanning in CI (M0-P5: gitleaks over the full git history, pinned image, redacted output)

### Audit and monitoring
- [x] Append-only audit events for FR-AUD-01 actions, written in the same transaction (M1-P4: `uow.audit` shares the change's transaction, so a failed audit insert fails the change; sign-in, sign-in failure, sign-out, refresh reuse and staff role changes are recorded, with later actions added by the milestone that writes them)
- [x] Database role for the app cannot update/delete audit rows (M1-P4: two triggers refuse `UPDATE`, `DELETE` and `TRUNCATE` with `AUD_APPEND_ONLY` for every non-superuser role — a `REVOKE` would not bind the schema owner. A dedicated least-privilege role is M6-P1; lifting the guard is a documented, approved procedure, RUNBOOK §18)
- [x] Audit rows carry no personal data beyond IDs (M1-P4: metadata is capped to 20 short ID/enum values and the caller's IP is stored only as an HMAC under `AUDIT_IP_SALT`)
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
  an ADR and a privacy review before design starts. PRD v1.1 (C4) and ADR-0013 cover the M7
  assistant: no medical advice, tools limited to the user's own permissions, synthetic data only
  until a provider contract and a privacy review allow real patient data.
