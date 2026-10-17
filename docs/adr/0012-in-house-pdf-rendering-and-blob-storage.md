# ADR-0012: In-house PDF rendering and blob storage behind ports

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-17 |
| Deciders | Developer (M4 spec decisions 1a–5a), engineering |
| Related | FR-RX-04, FR-RX-06, NFR-07; spec `prescriptions.md` R8, R18, D1, D3; ADR-0005, ADR-0009 |

## Context

Issuing a prescription must produce a printable A5 (or A4) PDF with the clinic letterhead, the
doctor's registration details, and Hindi text that renders correctly (FR-RX-04, FR-RX-06). The PDF
is clinical content (C3): it may not leave infrastructure we control, and its text may not appear
in logs (NFR-07). The background worker that ADR-0005 describes arrives in M5, so M4 cannot render
in a job. CI must stay deterministic: no network calls and no output that changes with the
distribution's font packages.

Forces:

- Issued prescriptions are immutable (spec R6, P2 trigger), so a rendered PDF never goes stale: one
  render per version is enough.
- Two staff members may press *Print* on a fresh prescription at the same moment.
- The API container runs as a non-root user on a read-only root filesystem (ADR-0009).
- The patient page (P5) is HTML; one layout vocabulary for both the page and the PDF is cheaper to
  keep consistent than two.

## Decision

Render and store PDFs in-house, behind two ports, on first request.

**`PdfRendererPort`** — `render(document: RxDocument) -> bytes`. `RxDocument` is a plain view model
(clinic, doctor snapshot, patient summary, items with their structured phrases already resolved
into the prescription's language, advice, paper size). The port knows nothing about storage or
HTTP.

- Adapter: **WeasyPrint** (HTML + CSS → PDF), pinned in `pyproject.toml`, with a Jinja2 template
  (autoescaped) and print CSS for A5 and A4.
- Fonts: **Noto Sans** and **Noto Sans Devanagari** (SIL Open Font Licence 1.1) vendored as files in
  the adapter package with their SHA-256 recorded and the licence alongside, loaded through
  `@font-face` from those files. Rendering does not depend on which fonts the image happens to
  have, so the same input gives the same text and layout on every machine and in CI.
- The renderer's URL fetcher refuses everything except the vendored font and stylesheet files: no
  network access, no `file:` outside the package (no SSRF through a crafted value).
- The API image gains WeasyPrint's native libraries (Pango and its dependencies) from the pinned
  Debian base; Trivy keeps scanning them.
- A test adapter returns a fixed small PDF so use-case tests do not depend on WeasyPrint; adapter
  tests render real PDFs and check their text with `pypdf` (dev dependency), not their bytes
  (PDFs carry creation dates).

**`BlobStoragePort`** — `put(key, data, content_type)` (write once: atomic, and an existing key is
left as it is), `get(key) -> bytes | None`, `exists(key)`.

- **Local volume adapter** for development, CI and tests: writes to a temporary file in the target
  directory, `fsync`, then `os.replace`, so a reader never sees half a file. The API mounts a named
  volume at `/var/lib/mediease/blobs` (the root filesystem stays read-only).
- **S3-compatible adapter** for production (any S3 API in the India region; wired in M6): `PUT` is
  atomic per object; server-side encryption required; bucket private, no public ACLs. Tested
  against an in-process S3 fake, never the network.
- The adapter is chosen by settings (`BLOB_STORAGE=local|s3`); `s3` needs its endpoint, bucket and
  credentials from the environment, never from code.

**Key and render-once.** The key is `rx/{clinic_id}/{prescription_id}/v{version}.pdf`. On
`GET /api/v1/prescriptions/{id}/pdf` the use case locks the prescription row `FOR UPDATE`, renders
and stores only if `pdf_object_key` is empty, records the key and commits. A second request waits
on the row lock and then finds the key, so two first requests cause one render. The wait is bounded
(`lock_timeout`); past it the caller gets `503 RX_PDF_BUSY` with `Retry-After`. `pdf_object_key` is
an operational column the immutability trigger allows to be set once.

**Delivery to the browser.** The API streams the stored bytes (`application/pdf`,
`Cache-Control: private, no-store`) after the permission check and the audit row. No pre-signed or
public URL is handed out: it would be a bearer link to clinical content that can travel in browser
history or forwarded messages. PDFs are small (tens of kilobytes), so proxying them costs little.

When the M5 worker exists, rendering may move into a job that calls the same port and the same
render-once use case; the HTTP path stays as the fallback.

## Alternatives considered

| Option | Pros | Cons | Why not chosen |
|---|---|---|---|
| Hosted document or media service (e.g. Cloudinary, a PDF API) | Nothing to install | Clinical content leaves our infrastructure; a processor agreement per vendor; CI needs the network or a mock that proves little | PHI must stay in-house (developer's decision) |
| ReportLab | Pure Python, small | Layout in code, a second layout from the patient page; weaker complex-script shaping for Devanagari | Hindi correctness and one layout vocabulary |
| Headless Chromium (Playwright) | Most faithful rendering | Several hundred MB in the API image, a browser to patch and sandbox | Image size and attack surface |
| Render inside the issue transaction | PDF ready at once | Issuing becomes slow and fails when rendering fails; the lock is held across a render on the busiest action | Render-on-first-request keeps issuing fast |
| Pre-signed storage URLs | Offloads bytes from the API | Bearer links to C3 data; the local adapter cannot sign | Streaming through the API keeps one audited gate |
| System font packages (`fonts-noto-core`) | No files in the repo | Large; output changes with distribution updates | Determinism; only two families are needed |

## Consequences

- Positive: no third party sees prescriptions; one gate (permission + audit) in front of every
  download; deterministic CI; Hindi rendered with a known font; storage swappable by settings.
- Negative / costs: the API image grows by WeasyPrint's native libraries; the first download of a
  version takes the render time (target < 1 s for a typical A5) while holding that prescription's
  row lock; the API serves PDF bytes; a named volume to back up locally (and a bucket in M6).
- `docs/SECURITY_AND_COMPLIANCE.md`: the M4 checklist item "PDFs via short-lived pre-signed URLs
  only" becomes "PDFs only through the authenticated, audited API; no public or pre-signed URLs".
- Follow-ups and triggers to revisit: move rendering into an M5 job if first downloads are slow at
  pilot volume; revisit Chromium only if WeasyPrint cannot render a format a pilot clinic needs
  (L-07); wire and test the S3-compatible adapter against the chosen India-region store in M6.
