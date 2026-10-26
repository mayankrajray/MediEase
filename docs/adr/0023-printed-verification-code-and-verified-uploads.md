# ADR-0023: A printed verification code, and uploads that only point to the database record

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 27 Oct 2026 |
| Deciders | Developer (architecture review and decisions D1–D7 approved 27 Oct 2026); MediEase engineering |
| Related | ADR-0003 (tenancy), ADR-0005 (job queue), ADR-0012 (PDF rendering and blob storage; this ADR extends its layouts without editing it), ADR-0013 (LLM gateway), ADR-0015 (patient accounts), ADR-0024 (assistant); PRD v1.3 C15–C16, FR-RX-11, FR-UPL-01..05, NFR-20; specs `assistant.md`, `prescription-uploads.md`; `docs/milestones/M7-architecture-review.md` |

## Context

M7 lets a patient (or someone holding a patient's paper) give the assistant a MediEase
prescription by uploading a photo or the PDF. MediEase must never accept arbitrary external
prescriptions, and nothing read off an uploaded file may become clinical information: a genuine
QR code pasted onto edited medicine lines must not get the edited lines explained. Before M7 the
printed page carried no identifier at all (the UUID was only in the download file name), the
renderer refused every image, nothing scanned files for malware, and the single worker ran every
job kind one after another.

## Decision

1. **Layout 3 prints a verification code.** Every version issued from M7a-P1 prints its own
   `prescriptions.id` (UUIDv7, no new identity) as text ("Verification code") and as a QR code
   whose payload is exactly `MEDIEASE-RX:1:<uuid>`. Both sit in the page's bottom margin boxes
   (running elements), with the MediEase mark, on every page, outside anything a clinic or doctor
   writes. The QR is drawn as inline SVG (`segno`) and the mark is a vendored inline SVG, so the
   ADR-0012 fetcher stays closed. Layouts 1 and 2 are frozen; versions issued on them can never
   be verified by upload (paper outlives the change; they use the portal or the link).
2. **The payload is opaque and unsigned.** No name, phone, clinic, medicine or date; not a URL;
   not the patient link token. It grants nothing: it is resolved only inside the uploader's own
   access, so a signature would add key management to paper that lives for years for no gain.
3. **The upload is a pointer, never a source.** An upload is quarantined, scanned by ClamAV,
   read for the identifier only (QR, then the PDF text layer; no OCR in the first release; a
   typed code is the fallback), verified, and then deleted. The extraction port returns an ID or
   nothing: extracted text never leaves the adapter. After verification the assistant reads the
   **database record** through the portal use cases; upload bytes, extracted text and blob keys
   are never given to it (an import-linter contract and tests enforce this).
4. **Verification uses the existing access model.** If the version is in the account's
   `PortalScope` (its own linked records), it is verified as `OWN`. Otherwise the uploader must
   pass the prescription chain's existing last-4 check (FR-RX-08) from a verified account: the
   same proof the patient link asks for, on the same lockout. A pass gives a **representative
   grant** limited to that one prescription chain for 24 hours; it never links a record, so
   appointments, bills and other prescriptions stay out of reach. A code that is not the
   account's always gets the challenge, whether or not it exists, so the response is no
   existence oracle; the clinic is found by a reviewed IDs-only lookup (as ADR-0003 allows), never
   by a tenancy bypass.
5. **Superseded versions are never substituted.** An older version is verified as itself and
   flagged; the user explicitly chooses the uploaded (historical) version or the latest, and
   the choice is stored on the upload and used by the assistant.
6. **A separate upload worker.** The worker claims job kinds by queue (`WORKER_QUEUE=default` or
   `uploads`), so scanning never delays reminders; the upload worker mounts the blob volume and
   reaches clamd on the compose network. ClamAV runs as its own container behind a
   `MalwareScannerPort` (clamd `INSTREAM`, standard-library socket). An unavailable scanner fails
   closed after retries.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Visible UUID only | Nothing to draw | Phone photos need OCR of 36 characters | Unreliable; brings an OCR engine |
| HMAC-signed payload | Proves MediEase printed it | Keys outlive rotation on paper; adds nothing to an account-scoped lookup | Not needed for the threat |
| Tesseract or PaddleOCR | Reads the printed code from photos | System packages or a large runtime; slow on CPU | QR plus text layer plus typed code covers the cases; revisit Tesseract only on pilot evidence |
| Let the model read the upload (multimodal) | "Understands" any document | Edited content becomes advice; data to a provider | Breaks the source-of-truth rule |
| Link the uploader to the record | Reuses portal access | A paper copy would open the whole record | Too much access for possession of one prescription |
| Look the prescription up by ID for anyone | Simple | An oracle for IDs; a tenancy bypass | Forbidden (AGENTS.md §7) |

## Consequences

- Positive: an upload can only ever open a record MediEase issued and the uploader may see; the
  assistant's clinical text always comes from the database; scanning cannot slow reminders.
- Negative / costs: prescriptions issued before layout 3 cannot be verified by upload; ClamAV
  adds a container needing about 1–1.5 GB of RAM and outbound access for `freshclam`; a
  malicious uploader holding the paper can spend the chain's five last-4 attempts (the same risk
  as a forwarded link; staff can reset it).
- Follow-ups: replace the placeholder mark with the official logo; measure the "no identifier"
  rate in the pilot before considering Tesseract; egress restrictions for the upload worker in
  M9.
