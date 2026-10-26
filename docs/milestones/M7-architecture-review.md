# M7 architecture review: MediEase-issued prescription verification for patient uploads

| Field | Value |
|---|---|
| Date | 27 Oct 2026 |
| Type | Architecture review only. No code, schema, template, ADR, PRD or plan was changed |
| Inspected at | local branch `m6d/63-billing-and-documents` @ `e115c92` (the M6d head; `main` was not pulled locally) |
| Status | **Awaiting developer approval** |

---

## 1. VERDICT

**`FEASIBLE WITH SMALL ARCHITECTURAL CHANGES`**

What already supports the design:

- The PDF layout is code, not data. Layouts are versioned in `adapters/pdf/weasy.py` (`LAYOUTS`),
  and each prescription is frozen to a `layout_version` when it is issued. A fixed MediEase layer
  is therefore guaranteed by construction, because clinics cannot change the layout.
- Every prescription version already has a stable UUIDv7 primary key (`prescriptions.id`). That
  identifier needs no new column.
- The ownership check already exists and does not bypass tenancy. `issued_in_scope(PortalScope.read(uow, account_id), rx_id)`
  in `application/portal/records.py` resolves a prescription ID only inside the account's linked
  (clinic, patient) pairs. A prescription that is not the account's is simply "not found".
  Looking up the identifier and verifying ownership are the same operation, so the design needs
  no cross-clinic lookup port.
- The pieces for uploads, storage and background work exist:
  - magic-byte sniffing (`domain/shared/files.py`)
  - a write-once blob store with `delete` (`ports/storage.py`)
  - the attachment upload pattern (`application/visits/attachments.py`)
  - a PostgreSQL job queue with dedupe, `SKIP LOCKED`, retries and idempotent chaining
    (`adapters/db/jobs.py`)
  - per-account and per-IP rate-limit buckets
  - ID-only audit events

What is missing or in tension (none of it needs a redesign):

- **No clinic template customization exists.** The brief assumes clinics customize their
  template, but the only layout-related clinic setting is `rx_paper_size` (A5/A4). The
  "letterhead" is the text fields in `ClinicSnapshot`. Clinics have no logo, colours, section
  toggles or HTML. Clinic logos are a new feature.
- **Nothing identifies the prescription on the printed page today.** The UUID appears only in the
  download filename. No QR code is generated server-side, and the renderer's `AssetsOnlyFetcher`
  refuses every image.
- **No malware scanning, quarantine or scan state exists anywhere.** `docs/specs/visit-attachments.md`
  lists patient uploads, OCR and virus scanning as out of scope.
- **Uploads are not in M7's scope**, and the security policy gates them.
  `SECURITY_AND_COMPLIANCE.md` §4 says any new AI feature needs "a PRD update, an ADR and a
  privacy review before design starts". ADR-0013 allows only synthetic data to reach the LLM
  provider.
- **Old prescriptions can never carry the identifier.** PDFs are rendered once and stored, and
  layouts are frozen at issue. Only prescriptions issued after the new layout ships can be
  verified.

One design correction is central to everything below. **After verification, the AI must use the
database record, never the uploaded image or its OCR text.** If the AI reads the upload's content,
a forger can paste a genuine QR code onto altered medicine lines and have the forgery processed.
That would break the principle that the UUID and the database are the source of truth. Once the
upload is verified it has served its purpose: it is a key to a record MediEase already holds in
structured form. As a result, the "AI/document-processing" stage becomes "bind the verified
prescription ID to the assistant". No document AI is needed, and no image goes to an LLM.

---

## 2. CURRENT ARCHITECTURE FINDINGS

### 2.1 Prescriptions

| Fact | Where |
|---|---|
| `prescriptions.id` is a UUIDv7 primary key. Each revision is a new row (new id, `version+1`, `supersedes_id`), and issuing it marks the older version `SUPERSEDED` | migration `0010_prescriptions.py`; `domain/prescriptions/prescription.py` `revision_of`, `issue`, `supersede` |
| An issued row is immutable, enforced by a PL/pgSQL trigger. Only `status`, `pdf_object_key` (set once), `link_delivery` and `updated_at` may change | `0010_prescriptions.py` `_OPERATIONAL` |
| `layout_version` is frozen at issue (`CURRENT_LAYOUT`), with a `CHECK >= 1` and no upper bound | `0013_patient_links.py`; `Prescription.issue` |
| `clinic_snapshot` (JSONB) is the whole letterhead: name, address, city, state, pincode, phone | `ClinicSnapshot` |
| The PDF is rendered on first download and stored write-once at `rx/{clinic}/{rx_id}/v{n}.pdf` | `application/prescriptions/pdf.py`; `document.py` `pdf_object_key` |
| Printed identifiers today: patient name, patient code (`ME-0142`), age, sex, date, the revision note, the footer "Digitally generated via MediEase". **There is no prescription identifier** | `document.py` `build_document`; phrasebook |
| There is no human-readable prescription number. Bills have one (`SC/26-27/0001`), so the pattern exists if a number is ever wanted | `domain/billing/bill.py` |

### 2.2 Template and renderer

| Fact | Where |
|---|---|
| WeasyPrint 70.0 with Jinja2 autoescape and StrictUndefined. Layout 1 is `prescription.html.j2`; layout 2 is `prescription-2.html.j2` plus the medicine schedule. The code comment says "Never edit a released layout: add the next one" | `adapters/pdf/weasy.py` `LAYOUTS` |
| `AssetsOnlyFetcher` serves only four vendored TTF fonts. Any other URL, including `data:` URIs and images, aborts the render | `weasy.py` |
| Clinic customization is `rx_paper_size` only, through `PATCH /api/v1/clinic` with `extra="forbid"`. Clinics have no logo, colours, HTML or section toggles. `rx_templates` are the doctor's medicine and advice content, not layout. FR-TPL (specialty templates) is in the backlog | `delivery/http/clinic.py`; `domain/clinics/clinic.py`; PRD §7 |
| QR codes exist only in the web app (the npm `qrcode` package), for the patient link, receipt and portal invite. No Python QR library is installed and no PDF contains a QR code | `features/prescriptions/PrintAndLink.tsx`, `ReceiptPanel.tsx`, `PatientPortalCard.tsx` |
| The patient link token is HMAC-signed and carries `cid` (clinic) and `rid` (version-1 id). It is about 100 characters, expires after at most 90 days, and opening it needs the last-4 phone challenge | `domain/links/token.py`; `application/links/use_cases.py` |

### 2.3 Accounts, ownership and tenancy

| Fact | Where |
|---|---|
| `patient_accounts` is global. `patient_account_links` is a tenant table allowing one active link per (clinic, patient) and per (clinic, account). One account can link to records in many clinics | `adapters/db/models/portal*.py` |
| Links are created only from proof the clinic gave: an invite, the prescription link plus last-4 check, or an accepted booking. **Never by phone, name or a matching identifier alone** | FR-PRT-02/06; `application/portal/linking.py`; SECURITY §3 |
| `PortalScope.read` lists active links through the reviewed, IDs-only `SqlAlchemyPortalLookup`, skips suspended clinics, then reads through `uow.tenant(clinic_id)` | `application/portal/scope.py`; `adapters/db/portal_links.py` |
| `issued_in_scope` accepts only `ISSUED` versions of a linked record. A superseded version is `NotFound` | `application/portal/records.py` |
| Tenancy: every tenant query goes through `TenantScopedRepository`. Cross-clinic reads are separate reviewed lookup classes, never a flag | `adapters/db/tenancy.py`; AGENTS.md §7 |

### 2.4 Uploads, storage and jobs

| Fact | Where |
|---|---|
| The sniffer recognises the `%PDF-`, JPEG and PNG signatures only and parses nothing. A polyglot or malicious PDF with a valid header passes | `domain/shared/files.py` |
| Attachment pattern: multipart, `max_content_length`, the whole file read into memory, blob first then the row, the blob deleted if the commit fails. No `status`, `sha256` or scan columns | `delivery/http/attachments.py`; `application/visits/attachments.py`; `0040_visit_attachments.py` |
| The blob store is one root or bucket, separated by key prefix. It stores whole bytes, is write-once, has no signed URLs, and S3 objects get SSE-AES256 | `ports/storage.py`; `adapters/storage/{local,s3}.py` |
| The job payload holds IDs only. `clinic_id IS NULL` only for kinds listed in `ck_jobs_system_kind`, so a new system kind needs a migration (precedents: 0016, 0017, 0021, 0031, 0032) | `domain/jobs/job.py`; `0014_jobs.py` |
| One worker claims **any** kind and runs jobs serially, so slow scan or decode jobs would delay reminders and messages | `adapters/db/jobs.py` `_CLAIM`; `delivery/worker/loop.py` |
| The `worker` container does **not** mount the `blobs` volume, and its `/tmp` is a 1 MB tmpfs | `docker-compose.yml` |
| Containers are hardened (`read_only`, `cap_drop: ALL`, `no-new-privileges`) and `scripts/smoke.sh` checks it. There are no custom networks or resource limits | `docker-compose.yml`; `scripts/smoke.sh` |
| The API image is `python:3.12.15-slim-trixie` (Debian 13); `apt` packages are scanned by Trivy in CI | `apps/api/Dockerfile`; `.github/workflows/ci.yml` |
| No OCR, QR, image or PDF-parsing library is installed at runtime. `pypdfium2` is a dev dependency, used by tests | `apps/api/pyproject.toml` |
| **Issue #30 (open):** an upload over 2 MB through the web origin can return 500 instead of 413 | `NEXT_STEPS_PLAN.md`; RUNBOOK |

### 2.5 M7 and policy

- M7 today covers FR-AI-01..03: the LLM gateway, tools with the user's permissions and a
  confirmation step for writes, guard rails, the patient and staff assistants, and the landing
  page. **No document mentions uploads, OCR, ClamAV or external prescriptions for M7.** There is
  no `docs/milestones/M7*.md`.
- PRD principle 6 and §6.3 make AI clinical decision support a non-goal. FR-AI-02 says the
  assistant never interprets content beyond restating the doctor's own words.
- ADR-0013: "only synthetic data is sent" until a provider contract and a privacy review allow
  more. Tool results carry only what the screen would show.

---

## 3. REQUIRED CHANGES

Smallest set, grouped as requested. **E** marks an extension of an existing file or module,
**N** a new file or module.

### Prescription and template generation
- **E** `adapters/pdf/weasy.py`: add **layout 3** (`prescription-3.html.j2`, `prescription-3.css`)
  to `LAYOUTS`. Layouts 1 and 2 stay untouched.
- **E** `domain/prescriptions/prescription.py`: `CURRENT_LAYOUT = 3`.
- **E** `domain/prescriptions/document.py`: `RxDocument` gains `verification_code` (the printed
  identifier text) and `qr_payload`. `build_document` fills them from `rx.id` for layout 3 or later.
- **E** `weasy.py` `AssetsOnlyFetcher`: add the vendored MediEase logo to the allow-list. Generate
  the QR code as **inline SVG** in the adapter, so no URL is fetched and the fetcher stays closed.
- **N** a vendored `assets/mediease-logo.svg`. A placeholder can be used until the official logo
  arrives.
- **E** the phrasebook: the "Verification code" label in English and Hindi.
- *Optional, separable:* clinic logo. This needs `clinics.logo_key`, an upload endpoint reusing the
  attachment validation, a content-addressed key such as `clinic-logos/{clinic}/{sha256}.png`
  (write-once, so it is effectively immutable), and `ClinicSnapshot.logo_key` (JSONB, so no
  `prescriptions` migration). The fetcher would serve those bytes through a controlled internal
  scheme. **The clinic logo has no security value** (anyone can copy a logo), so it is branding,
  not part of verification.

### Database and schema
- **N** migration: the `prescription_uploads` table (§5.2). It is **account-owned and not tenant
  data until verified**, like the ADR-0020 platform-data precedent:
  - `id`, `account_id`, `state`, `content_type`, `size_bytes`, `sha256`, `quarantine_key`
  - `clinic_id` and `prescription_id`, both nullable and set only at verification
  - `rejection_code`, timestamps
  - CHECKs: `(state = 'VERIFIED') = (prescription_id IS NOT NULL AND clinic_id IS NOT NULL)`, plus
    content type and size bounds
- **E** the same migration: `ck_jobs_system_kind` gains the intake kinds (the upload has no clinic
  before verification).
- **Not needed:** a new identifier column (`prescriptions.id` is the identifier); a
  `layout_version` change (no upper bound); a `pdf_sha256` column (hash the stored blob on demand,
  which avoids touching the immutability trigger).
- **E** `docs/DATA_MODEL.md`.

### Upload and storage
- **N** `delivery/http/portal_uploads.py`: `@patient`, multipart, `max_content_length`, sniffed
  PDF/JPEG/PNG only, 10 MB.
- **N** `application/uploads/`: an `UploadPrescription` use case that writes the file to a
  quarantine key `quarantine/{account_id}/{upload_id}`, inserts the row as `QUARANTINED`, enqueues
  the scan job in one transaction, and reuses the attachment blob-then-row cleanup.
- **E** `docker-compose.yml`: mount the `blobs` volume on the intake worker (or use S3).
- **Fix first:** issue #30 (413 through the web origin), because patient uploads go through Next.js.

### Malware scanning
- **N** `ports/malware.py` (`MalwareScannerPort.scan(bytes) -> Clean | Infected(name) | Unavailable`)
  and `adapters/malware/clamd.py`, using the clamd `INSTREAM` protocol over TCP with the standard
  library `socket` (no new dependency), and a fake adapter for tests.
- **E** `docker-compose.yml`: a `clamav` service (official image, pinned by digest), a signature
  volume, a long `start_period`, and a health check. It is not on a host port and is reached only
  by the intake worker.
- **E** `scripts/smoke.sh`: include it, or record a justified exception (its entrypoint may need
  to own its signature directory, the same reason `db` is not hardened).
- Fail closed: `Unavailable` is retried, then the upload is `REJECTED (SCAN_UNAVAILABLE)`. Never
  pass a file through unscanned.

### Identifier extraction
- **N** `ports/identifier_reader.py` and `adapters/extraction/`:
  1. **PDF:** read the text layer with `pypdfium2` (promoted to a runtime dependency; wheels only,
     no system packages). MediEase PDFs contain the code as real text. Then rasterise page 1 for
     the QR code.
  2. **Image or rasterised PDF:** decode the QR code with `zxing-cpp` (wheels, no system package).
  3. *Optional fallback, deferred:* Tesseract on the code line (§6).
- Domain parser: accept only the exact `MEDIEASE-RX:1:<uuid>` grammar. Anything else is
  `NO_IDENTIFIER`.
- Limits before decoding: page count of 1–2, a pixel cap against decompression bombs, a time cap.
- Add an import-linter rule so decoders are imported only in `adapters/`.

### Patient ownership verification
- **Reuse** `PortalScope` and `issued_in_scope`, with one small extension: accept a `SUPERSEDED`
  version of a linked record and resolve it to the chain's current `ISSUED` version (or reject it
  as `UPL_SUPERSEDED`; this is decision D3).
- **Optional, strongest signal:** if the upload is a PDF and its `sha256` equals the sha256 of the
  stored `pdf_object_key` blob, record `byte_exact = true`.
- Do **not** create a link from an upload. A printed UUID is not proof under FR-PRT-02. An unlinked
  account gets `NOT_FOUND` and is told to use the prescription link or ask the clinic.

### AI and document processing
- **No document AI.** On `VERIFIED`, the assistant (M7) receives only the `prescription_id`. Its
  tools read the record through the existing `GetPortalPrescription` and medicine-plan use cases.
  The LLM never receives image bytes, OCR text or blob keys.
- **E** the M7 tool layer: a `prescription_from_upload(upload_id)` tool that requires
  `state = VERIFIED` and the caller's account, and returns the portal view.
- An import-linter contract: assistant modules may not import the upload storage or extraction
  adapters.

### API
- **E** `contracts/openapi.yaml`:
  - `POST /api/v1/portal/prescription-uploads` returns 202 with `{id, state}`.
  - `GET /api/v1/portal/prescription-uploads/{id}` returns the state and a rejection code only.
  - Optionally `DELETE` it.
- **E** `docs/API.md` and `docs/ERRORS.md`: new codes `UPL_TYPE`, `UPL_SIZE`, `UPL_INFECTED`,
  `UPL_SCAN_UNAVAILABLE`, `UPL_NO_IDENTIFIER`, `UPL_NOT_FOUND`, `UPL_SUPERSEDED`,
  `UPL_RATE_LIMITED`.
- Rate limits: `rx-upload-account:{id}` and `rx-upload-ip:{hash}`.

### Frontend
- **N** `apps/web/src/features/uploads/` and a portal page: a file and camera input, a state poll,
  and plain-language rejection messages. When the upload is verified, link to the existing
  prescription page.
- **E** generated types (`make contract`).
- Staff screens are not needed unless decision D6 says otherwise.

### Tests
- Renderer: layout 3 always contains the code and the QR code at a fixed position, for A5 and A4,
  English and Hindi. A round trip renders a PDF, rasterises it, decodes the QR code and gets
  `rx.id`. Layouts 1 and 2 are byte-stable.
- State machine: no transition skips a stage. A database CHECK test shows `VERIFIED` cannot exist
  without `prescription_id`.
- Scanner: the EICAR test file is rejected. `Unavailable` retries, then rejects.
- Extraction: a photo, a blurred photo, a rotated image, a PDF, a forged QR code with a random
  UUID, another account's UUID, a superseded version, and a decompression bomb.
- Tenancy: a cross-account case in `tests/tenancy/test_portal_scope.py` (the existing guard fails
  without one).
- Privacy: logs and audit rows carry no file name, OCR text or medicine.
- AI: the assistant cannot reach a non-`VERIFIED` upload, and an LLM-call spy shows no image or
  extracted text is sent.

### Security and privacy
- Close the open "File uploads" item in SECURITY §3. Its "served via signed URL" text contradicts
  ADR-0012 and must be corrected.
- Classify uploads as **C3**. Delete the quarantined file after verification or rejection, keeping
  only the hash, state and IDs. Retention is a short period such as 24 h, to be confirmed under
  L-04.
- Uploaded bytes are never served back to staff or patients (decision D6).
- The intake worker gets no outbound network (the compose network for clamd and the database only)
  and memory and CPU limits.
- Do the privacy review required by SECURITY §4. Because no image or text reaches the LLM, the
  review is narrow.

---

## 4. UUID / QR DESIGN

### Template architecture (question 3)

The current system **can guarantee** a fixed MediEase layer, because of how the code is built:

- Clinics control no layout, only `rx_paper_size` and letterhead text.
- Layouts are code and are frozen per prescription at issue.
- The renderer fetches nothing that is not vendored.

Placing the identifier block in layout 3's `@page` margin box (e.g. `@bottom-right`, beside the
existing footer) makes it appear on **every page** at a fixed position relative to the page edge,
for both A5 and A4, independent of content length. Neither clinic data nor doctor content can
move or hide it.

The smallest change is layout 3. If clinic branding is ever added (a logo, or FR-TPL), keep the
same rule: clinics supply **values** through validated fields (a logo blob, colours from an
allow-list), never markup, and the identifier zone stays a fixed margin box that the template
system cannot address.

### Recommendation: visible code **and** QR code

| | Visible UUID only | Visible UUID + QR code |
|---|---|---|
| Phone-photo reliability | Needs OCR of 36 characters, which is error-prone with skew, blur and glare | QR has built-in Reed–Solomon error correction and decodes from skewed, partial, low-light photos |
| Digital PDF | Exact, from the text layer | Exact, from the text layer (the QR code is not even needed) |
| Dependencies | Tesseract (system package and language data) | `zxing-cpp` wheel. OCR becomes optional |
| Manual fallback | Typing 36 characters | The same typed fallback is still printed |
| Print cost | None | About 18–22 mm square, which fits A5 |

**Recommend the visible code plus a QR code.**

**QR payload:** `MEDIEASE-RX:1:<prescription_uuid>`. The version tag allows later changes, and it
uses the canonical lower-case UUID of the **issued version** (`prescriptions.id`, not the
version-1 chain ID).

- It is opaque. It holds no name, phone, clinic name, medicine or date.
- It is deliberately **not a URL**. A scanned code opens nothing, and no endpoint is exposed to
  pharmacists' cameras.
- It is **not the patient link token**. That token expires after at most 90 days (paper outlives
  it), acts as a bearer credential for viewing, and grants the linking proof. None of that belongs
  on paper.
- Error correction level M or Q.

**Visible text:** the same UUID in a monospace face, labelled "Verification code" in English and
Hindi, for example `0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d`.

**Is an HMAC on the payload needed? No.** Verification is an account-scoped database lookup. A
guessed or forged UUID that is not in the caller's own linked records is "not found", and
UUIDv7's 74 random bits make guessing pointless. An HMAC would add key management to paper that
lives for years, for no gain. Revisit only if an **unauthenticated** verify endpoint is ever added.

**What the code proves, and what it does not:** a valid code proves that the paper refers to a
real MediEase prescription of this account. It does **not** prove the paper's content is
unaltered. That is why only the database record is processed (§5). The PDF `sha256` match proves
byte-exact authenticity when the patient uploads the original file.

---

## 5. VERIFICATION FLOW

### 5.1 Ordering: feasible as proposed

```
POST upload (@patient, rate limited, sniffed type, ≤10 MB)
  → blob quarantine/{account}/{upload} + row QUARANTINED + job scan_upload        [one transaction]
scan_upload (intake worker → clamd INSTREAM)
  → INFECTED | SCAN_UNAVAILABLE ⇒ REJECTED, delete blob
  → clean ⇒ SCANNED + job extract_identifier
extract_identifier (limits; PDF text layer → QR; optional OCR)
  → none ⇒ REJECTED(NO_IDENTIFIER), delete blob
  → found ⇒ IDENTIFIED(candidate_uuid) + job verify_upload
verify_upload (PortalScope.read(account) → issued_in_scope(candidate))
  → not in scope ⇒ REJECTED(NOT_FOUND), delete blob
  → in scope ⇒ VERIFIED(clinic_id, prescription_id), delete blob, audit
assistant (M7) ← only VERIFIED uploads, only prescription_id, DB record via portal use cases
```

- Each stage advances the row and enqueues the next job in the same transaction, with a dedupe key
  `upload_<stage>:{id}`. This is the existing outbox pattern. Every stage is idempotent and
  re-checks the current state before acting.
- Extraction comes after scanning on purpose: extraction parses untrusted files.
- The intake kinds should run on a **separate worker** with a kind filter on `_CLAIM` (a small
  change, `AND kind = ANY(:kinds)`), so decoding cannot delay reminders. This needs its own
  container with the `blobs` mount, no egress, and memory limits.

### 5.2 States

`QUARANTINED → SCANNED → IDENTIFIED → VERIFIED`, with `REJECTED(code)` reachable from every
state. The rules are enforced in the domain entity **and** by the database CHECK. `VERIFIED` is
the only state that carries `prescription_id` and `clinic_id`.

### 5.3 Can the AI be completely prevented from processing an unverified prescription? **Yes.**

Four layers enforce it:

1. **Data:** an unverified row has no `prescription_id` (database CHECK). There is nothing to
   process.
2. **Tooling:** the only assistant tool that touches uploads requires `VERIFIED` and the caller's
   own `account_id`, then reads the database record through `PortalScope`. No tool returns blob
   bytes, blob keys or extracted text.
3. **Code boundaries:** import-linter forbids assistant and LLM modules from importing the upload
   storage or extraction adapters. The extraction stage never calls `LlmPort`.
4. **Tests:** a spy `LlmPort` asserts that no message contains upload bytes or extracted text, and
   that an unverified `upload_id` is "not found".

Because the AI only ever sees the database record, even a **verified** upload cannot inject altered
content. That is stronger than the original design.

**Secondary consistency checks (OCR of the patient name):** recommend **none**. The lookup is
already scoped to the account's own records, so a name check adds no security, and OCR of Hindi
names on photos would mostly produce false mismatches.

---

## 6. TESSERACT vs PADDLEOCR

**For most uploads, OCR is unnecessary.**

- Digital MediEase PDFs, likely the majority since patients receive PDFs from the portal, contain
  the code as real text and are read exactly with no OCR.
- Photos and scans are handled by the QR code, which decodes far more reliably from phone photos
  than OCR of a 36-character hex string.
- OCR would only be a third-tier fallback, for a photo where the QR code is unreadable but the
  printed code is legible. That is a narrow case, and in the same case a retake prompt or typing
  the code also works.

**Recommendation:** ship M7 **without OCR**, using the PDF text layer, the QR code (`zxing-cpp`)
and a "retake photo or type the code" fallback. Measure the `NO_IDENTIFIER` rate in the pilot. If
OCR is ever justified, choose **Tesseract**, constrained to a single line (`--psm 7`) with the
allow-list `0-9a-f-`, on the crop next to the QR finder pattern, with the UUID grammar as the
validator. **Do not use PaddleOCR.**

| Criterion | Tesseract (fallback only) | PaddleOCR |
|---|---|---|
| Known, fixed template; one line in a known spot | Good on clean printed Latin hex in a monospace face | Its strength (layout detection, scene text) is not needed |
| What must be read | `[0-9a-f-]`, 36 characters, a known grammar | Overkill |
| Hindi or English text | Irrelevant: OCR must not read content, and the code is Latin | Better Devanagari, but irrelevant here |
| Logos | Ignored (crop) | Ignored |
| Phone-photo quality | Weak on skew and blur, but the QR code covers that case | Stronger, but QR is stronger still |
| CPU and RAM | Tens of MB, about 100–300 ms per crop | The PaddlePaddle runtime and models take hundreds of MB to over 1 GB RAM and are slower on CPU |
| Image size and dependencies | `apt tesseract-ocr` plus `eng` data, about 30–50 MB, Debian-patched and Trivy-scanned | A large pip tree (paddlepaddle, opencv, numpy, models), a bigger CVE surface, and Python 3.12/trixie wheel risk |
| Deployment | One `apt` line. Needs `/tmp` larger than the worker's 1 MB tmpfs | Model downloads at runtime or baked in, and a heavy image |
| Maintainability | Stable for decades | Frequent breaking releases |

**ClamAV** remains the scanner. There is no architectural reason to drop it, but note:

- clamd needs about 1–1.5 GB RAM and outbound access for `freshclam`. Run it as its own service
  and do not add it to the API image.
- Its entrypoint may conflict with `x-hardened`.
- It catches **known** malware signatures, not zero-day exploits in the decoders. The real
  controls against those are the type allow-list, size, page and pixel caps, an isolated intake
  worker with no egress, and never serving the upload back to anyone.

---

## 7. M7 PHASE PLACEMENT

**Confirmed: this must be decided before uploads and the AI pipeline.** It must also come before
anything else that depends on printed prescriptions, because **only prescriptions issued after
layout 3 ships can ever be verified**. Every week layout 3 is delayed adds prescriptions that can
never be uploaded.

The code suggests three refinements to the proposed order:

1. **Move the template and identifier change to the front, and spike extraction against it before
   building uploads.** Render layout 3, rasterise it, and decode the QR code and text layer in
   tests. This fixes the QR size and position with evidence, and it needs no upload code.
2. **The LLM gateway and guard rails (the existing M7-P1 and P2) are independent** of the upload
   pipeline and can proceed in parallel or first. Only the final assistant integration depends on
   both.
3. **The "AI/document processing" stage collapses** into a tool binding on `VERIFIED`. It is not a
   separate pipeline phase.

Recommended order:

```
P0  Design + ADR + PRD/req IDs + privacy review          (this review → approval)
P1  Layout 3: MediEase logo, code, QR (+ extraction round-trip tests)   ← ship early
P2  LLM gateway (Groq, console adapter)                  ← independent, existing M7 scope
P3  Tools + guard rails                                   ← existing M7 scope
P4  Upload + quarantine + intake worker (+ fix issue #30)
P5  ClamAV service + scan stage
P6  Identifier extraction + DB/ownership verification (+ delete on outcome)
P7  Patient assistant incl. verified-upload tool; staff assistant
P8  Landing page + demo rehearsal                         ← existing M7 scope
(—) Clinic logo: optional, separate phase or deferred
```

---

## 8. PRD / ADR / MIGRATION IMPACT

| Question | Answer |
|---|---|
| Fits the existing M7 scope? | **No.** M7 is FR-AI-01..03. Uploads, scanning and the printed identifier are new, and the visit-attachments spec explicitly excluded patient uploads, OCR and antivirus. Adding them to M7 is a scope change that needs your decision. |
| New requirement IDs? | **Yes.** Suggested: `FR-RX-10` (every issued prescription prints the MediEase logo, a verification code and a QR code at a fixed position); `FR-UPL-01..05` (patient upload; quarantine and scan; identifier extraction; account-scoped verification; only verified uploads reach the assistant, and only as the database record); an NFR for malware scanning and upload retention. Optional: `FR-ORG-xx` for the clinic logo. |
| ADR? | **Yes, one new ADR** (next free number, 0023): "Verified patient prescription uploads", covering the identifier and QR payload, the quarantine state machine, ClamAV as a port, no OCR in v1 (Tesseract as the only sanctioned fallback), and no upload content to the LLM. Plus a short **amendment note on ADR-0012** (logo asset and inline-SVG QR, fetcher still closed) and a follow-up entry on **ADR-0013** (tools resolve verified uploads to the database record). |
| M7 phase plan changes? | **Yes.** From about 5 phases to about 8 (§7). Alternative, following the M6a–M6d precedent of one branch and one PR per milestone: **M7a** assistant (gateway, tools, guard rails, assistant, landing page) plus layout 3 shipped early, and **M7b** verified uploads plus the upload tool. M7a/M7b keeps each PR reviewable. |
| PRD changes? | **Yes.** A v1.3 change-log row; FR-RX-10 and FR-UPL in §8; an M7 row in §13. SECURITY §4 requires the PRD update before design starts. |
| Migration? | **Yes, one** for `prescription_uploads` plus the `ck_jobs_system_kind` change. A second only if the clinic logo is built (`clinics.logo_key`). **None** for the identifier itself or for layout 3. |
| Other docs | `DATA_MODEL.md`, `API.md`, `ERRORS.md`, `SECURITY_AND_COMPLIANCE.md` (§3 file-upload row corrected, §4 privacy review, sub-processors unchanged since no new external party), `RUNBOOK.md` (clamd operation and signature updates), `TESTING.md`, `GLOSSARY.md` ("verification code"). |

---

## 9. RECOMMENDED NEXT STEP

1. **You decide** (each has a recommendation):
   - **D1 Scope:** M7 split into M7a and M7b *(recommended)*, or one enlarged M7.
   - **D2 Payload:** `MEDIEASE-RX:1:<uuid>`, not a URL, no HMAC *(recommended)*.
   - **D3 Superseded upload:** accept it and show the current version with a "newer version"
     notice *(recommended)*, or reject it.
   - **D4 OCR:** none in v1, QR plus text layer plus manual entry *(recommended)*; Tesseract later
     only on evidence.
   - **D5 Clinic logo:** defer, since it has no verification value *(recommended)*, or include it
     as an optional phase.
   - **D6 Visibility:** uploads are never shown to staff and are deleted after the outcome
     *(recommended)*.
   - **D7 Purpose:** confirm what the patient gains from uploading when a linked account already
     sees every prescription in the portal. The likely answer is "point the assistant at the
     paper in my hand". If that is the only goal, a "choose from my prescriptions" picker gives the
     same result with no upload, and uploads could become a later convenience.
2. Then, on approval: close M6d in `TASKS.md`, branch M7 from an up-to-date `main` (the local
   checkout is still on `m6d/63-…`), and write the ADR, the PRD v1.3 rows, `docs/milestones/M7*.md`
   and the P1 spec. Implementation starts with layout 3.

Nothing has been implemented, committed or pushed. This file is untracked.
