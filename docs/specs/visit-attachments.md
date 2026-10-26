# Spec: Report attachments on visits

| Field | Value |
|---|---|
| Requirements | FR-VIS-04 |
| Milestone / phase | M6d / P6 (design: `docs/milestones/M6d-billing-and-documents.md`, decisions B8, D7) |
| Status | Approved 26 Oct 2026 (P2–P7 in advance) and built |
| Owner | Developer |
| Last updated | 2026-10-26 |

## 1. Context
Patients bring lab reports, scans and earlier prescriptions on paper or on their phone. Today they
stay in a folder at the desk or in the doctor's WhatsApp. P6 lets the clinic keep them with the
visit: a PDF or photo, private, opened only by clinical roles, and shown to the patient in the
portal when the doctor chooses.

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Front desk (`ATTACHMENTS_ADD`) | Attach a report to a visit (from the queue row), delete their own within 24 hours | List or open reports (`CLINICAL_VIEW`, D7); share |
| Owner (`ATTACHMENTS_ADD`, `CLINICAL_VIEW`) | Attach, list, open; delete their own within 24 hours | Share unless they are the visit's doctor |
| Doctor (`ATTACHMENTS_ADD`, `CLINICAL_VIEW`, `CLINICAL_WRITE`) | All of the above; the visit's doctor shares a report with the patient's portal or stops sharing | Delete another person's report |
| Patient (portal, linked record) | List and open the shared reports | See reports that are not shared |
| Another clinic | Nothing (404) | — |

## 3. Domain model
- **VisitAttachment** (`visit_attachments`, tenant): the visit and its patient, the storage key
  `attachments/{clinic}/{visit}/{id}`, the content type (`application/pdf`, `image/jpeg`,
  `image/png`), the size (1 byte to 10 MB), the cleaned file name (1–120 characters), who attached
  it and when, when and by whom it was shared (both or neither), and a delete as its time and
  author (both or neither). The row is never removed.
- The type sniffer (`domain/shared/files.py`) is shared with the M6c certificates.

## 4. Behaviour
- **R1** Anyone with `ATTACHMENTS_ADD` (every role) may attach a report to a visit of their clinic,
  in any status, locked ones too (reports often come later).
- **R2** The upload is `multipart/form-data` with one part `file`. The type is decided by the
  first bytes only: a PDF, JPEG or PNG; at most 10 MB. Otherwise 422 `VIS_FILE_REJECTED` with
  `details.reason` `type`, `size` or `missing`. A request well over 10 MB is 413 before it is
  read; anything but multipart is 415.
- **R3** A visit holds at most 20 reports that are not deleted (409 `VIS_ATTACHMENT_LIMIT`). The
  count and the insert happen under the visit row lock.
- **R4** The file is written to blob storage before the row. If the write fails the answer is 503
  `VIS_UPLOAD_FAILED`; if the row cannot be committed, the file is removed again.
- **R5** The name is the last path segment, without control characters, spaces collapsed, at most
  120 characters, with an extension that matches the real type (added when missing:
  `scan` → `scan.png`). It is shown and offered on download, never logged.
- **R6** `CLINICAL_VIEW` lists a visit's reports that are not deleted, oldest first, with
  `can_delete` for the caller.
- **R7** `CLINICAL_VIEW` opens a report: its stored type, `Content-Disposition: inline` with the
  name, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox; default-src 'none'`,
  `Cache-Control: private, no-store`.
- **R8** Its uploader may delete a report within 24 hours of the upload (403
  `VIS_ATTACHMENT_NOT_YOURS` for anyone else; 409 `VIS_ATTACHMENT_LOCKED` after). The row keeps
  the time and author; the file is removed (a failed removal is logged and the file is never
  served).
- **R9** A deleted report is not listed, opened, shared or shown in the portal (404).
- **R10** The visit's doctor (`CLINICAL_WRITE` and the visit's doctor profile, else 403
  `VIS_NOT_YOURS`) shares a report with the patient's portal or stops sharing. Repeating the current
  state changes nothing and records nothing.
- **R11** The portal lists the shared reports of every linked record, newest share first, 50 per
  clinic: name, type, size, clinic and the visit's day.
- **R12** The portal opens a shared report with the same headers as R7. Not shared, deleted or not
  the account's record is 404.
- **R13** Attaching, every staff open, deleting, sharing and unsharing are audited
  (`visit.attachment_added`, `_opened`, `_deleted`, `_shared`, `_unshared`) on the visit, with the
  attachment ID (and on adding the type and size). Never the name. Portal opens are not audited,
  like every portal read (patient-portal decision 7A).

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| POST | `/api/v1/visits/{visit_id}/attachments` | multipart `file` | 201 `VisitAttachment` | 403, 404, 409 `VIS_ATTACHMENT_LIMIT`, 413, 415, 422 `VIS_FILE_REJECTED`, 503 `VIS_UPLOAD_FAILED` |
| GET | `/api/v1/visits/{visit_id}/attachments` | — | 200 `VisitAttachmentList` | 403, 404 |
| GET | `/api/v1/visits/{visit_id}/attachments/{attachment_id}/file` | — | 200 the file | 403, 404 |
| DELETE | `/api/v1/visits/{visit_id}/attachments/{attachment_id}` | — | 204 | 403 `VIS_ATTACHMENT_NOT_YOURS`, 404, 409 `VIS_ATTACHMENT_LOCKED` |
| PUT | `/api/v1/visits/{visit_id}/attachments/{attachment_id}/share` | `{shared}` | 200 `VisitAttachment` | 403 `VIS_NOT_YOURS`, 404, 422 |
| GET | `/api/v1/portal/attachments` | — | 200 `PortalAttachmentList` | 401 |
| GET | `/api/v1/portal/attachments/{attachment_id}/file` | — | 200 the file | 401, 404 |

Contract 0.48.0; `Permission` gains `ATTACHMENTS_ADD`.

## 6. UI notes
The consultation screen gains *Reports* below the addenda: each report's name, type, size and
time, *Download*, *Share with patient* / *Stop sharing* for the visit's doctor, *Delete* for its
uploader within 24 hours, and *Attach a report* (a file input saying "A PDF, JPEG or PNG, at most
10 MB"; another type or a larger file is refused before sending). A queue row with a visit has
*Attach report…* in its menu for the front desk, which opens the same form in a dialog and says
"Report … attached for … at …". The portal's prescriptions page gains *Reports from your doctor*
(English and Hindi) with *Open* for each.

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| Report attached | `visit.attachment_added` | — | — |
| Report opened by staff | `visit.attachment_opened` | — | — |
| Report deleted | `visit.attachment_deleted` | — | — |
| Report shared, unshared | `visit.attachment_shared`, `visit.attachment_unshared` | — | — |

## 8. Edge cases
- A file named `report.pdf` that is an HTML page: refused (`type`); a PNG named `.pdf` is stored
  as a PNG with `.pdf.png`.
- Two uploads racing for the 20th place: the visit row lock lets one in; the other is 409.
- Blob storage down: 503 and nothing kept; on delete, the row says deleted and the file stays
  until removed by hand (RUNBOOK §31).
- A report shared, then deleted by its uploader within 24 hours: it leaves the portal at once.

## 9. Acceptance criteria
- **AC1** The front desk attaches a PDF to a visit and gets 201; it cannot list or open it (403).
- **AC2** A doctor lists and opens it; the response has `nosniff`, the sandbox CSP and
  `private, no-store`; each open adds one `visit.attachment_opened` row without the name.
- **AC3** An HTML file named `.pdf`, an empty file and a file over 10 MB are 422 with their reason;
  an 11 MB request is 413; JSON is 415.
- **AC4** Another person's delete is 403; the uploader's is 204 and the report is then 404; after
  24 hours it is 409 and the row keeps the delete's time and author.
- **AC5** The 21st report on a visit is 409.
- **AC6** Only the visit's doctor shares (the desk and an owner who is not a doctor get 403);
  the shared report appears in the linked account's portal and opens; an unshared one is 404.
- **AC7** Unsharing removes it from the portal.
- **AC8** Another clinic's visit and report are 404 for every route (NFR-08 suite), and another
  account's shared report is 404 (portal scope suite).
- **AC9** A blob store that refuses writes gives 503 and no row.

## 10. Observability
Logs `visit.attachment_added` (IDs, type, size), `visit.attachment_deleted`,
`visit.attachment_upload_failed`, `visit.attachment_cleanup_failed`, `visit.attachment_file_kept`
and `visit.attachment_missing` (error: a row whose file is gone). Never the file name or content.

## 11. Out of scope
Previews and thumbnails, OCR, virus scanning (only three types, never parsed or run), attaching to
a patient without a visit, sending a report by WhatsApp, and patients uploading.

## 12. Open questions
None.
