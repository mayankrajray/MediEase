# M7 completion report: AI assistant (M7a) and verified prescription uploads (M7b)

Date: 27 October 2026. Issue #65. Branch `m7/65-assistant-and-verified-uploads`, from
`origin/main` at `d53f53d`. Local only: nothing was pushed and no PR was opened, because pushing
needs the developer's explicit permission (AGENTS.md §7).

## 1. Status

All ten phases are built, tested, documented and committed: M7a P1-P5 (layout 3, the LLM gateway,
the assistant core, the patient and staff assistants) and M7b P6-P10 (upload and quarantine,
ClamAV on a separate upload worker, identifier extraction without OCR, verification, the handoff
to the assistant with cleanup and UI). Issue #30 is fixed. The issue's checklist is ticked.

What is left is the developer's part: permission to push the branch and open the milestone PR,
then CI and the merge review. Nothing else in M7 is open.

## 2. Commits

19 commits on the branch before this report, oldest first. Every subject follows Conventional Commits with
requirement IDs; every body explains what and why and ends `Refs #65`.

| Commit | Subject |
|---|---|
| `82754a3` | docs(m7): plan the assistant and verified uploads (FR-AI, FR-UPL) |
| `a6571f5` | feat(api): print the verification code and QR on layout 3 (FR-RX-11) |
| `143b06d` | feat(api): add the LLM gateway behind a port (FR-AI-03) |
| `f5bac83` | chore(api): format the LLM gateway tests |
| `b187058` | feat(api): add the patient and staff assistants (FR-AI-01, 02, 04) |
| `d09fc43` | feat(web): add the patient and staff assistant pages (FR-AI-01, 04) |
| `e69ead6` | test(web): add the assistant journeys (FR-AI-01, 02, 04) |
| `0e41274` | docs(m7a): record the assistant and layout 3 (FR-AI, FR-RX-11) |
| `a62810a` | feat(api): record verified prescription uploads (FR-UPL-01..05) |
| `a0b8937` | feat(api): scan uploads with ClamAV and read their ID without OCR (FR-UPL-02, 03, NFR-20) |
| `444d345` | feat(api): serve prescription uploads and typed codes (FR-UPL-01..05) |
| `4e3942b` | fix(web): answer oversized uploads with 413 at the web origin (#30) |
| `ce1c066` | feat(web): upload or type a prescription on the assistant page (FR-UPL-01..05) |
| `3417aba` | fix(web): start a new conversation when the upload's version changes (FR-UPL-05) |
| `7b49ad1` | test: add the upload journeys and the live ClamAV pipeline test (FR-UPL-01..05, NFR-20) |
| `fa38bec` | docs(m7b): record verified uploads, ClamAV and the #30 fix (FR-UPL-01..05, NFR-20) |
| `5dd640c` | test(web): say why journeys cannot start while the seeded session is full |
| `b5d735b` | test(web): expect the Assistant link in every role's menu (FR-AI-01) |
| `25dbf03` | docs(m7b): correct which queue make worker uses, and record the final e2e run |

This report is committed last, as `docs(m7): add the M7 completion report`, with `Closes #65`.

## 3. Files changed

130 files against `origin/main` (13,228 insertions, 103 deletions) before this report; the full
list is in the appendix. By area:

- **API, M7a:** `domain/assistant/` (guard rails, explanation, proposals, LLM types),
  `domain/prescriptions/verification.py`, layout 3 in `adapters/pdf/` (templates, CSS, the
  placeholder mark), `adapters/llm/` (console and OpenAI-compatible), `adapters/security/proposal_signer.py`,
  `application/assistant/` (engine, tools, patient, staff), `delivery/http/assistant.py`, `ports/{llm,assistant}.py`.
- **API, M7b:** `domain/uploads/`, `ports/uploads.py`, `application/uploads/` (intake, processing,
  verify, assistant), `adapters/db/{uploads.py,models/uploads.py}`, `adapters/extraction/identifier.py`,
  `adapters/malware/clamd.py`, `delivery/http/prescription_uploads.py`, migration `0042`, the job
  store's queue filter, settings, errors and `bootstrap.py`.
- **Web:** `/portal/assistant` and `/assistant` pages, `features/assistant/` (Chat, PortalAssistant,
  StaffAssistant, UploadPanel), `lib/api/limited-proxy.ts` and two route handlers for #30, i18n
  (English and Hindi), regenerated `schema.d.ts`, e2e `assistant.spec.ts` and `uploads.spec.ts`.
- **Platform:** `docker-compose.yml` (`clamav`, `upload-worker`, `WORKER_QUEUE`), `scripts/smoke.sh`,
  `.env.example`, `apps/api/pyproject.toml`, `contracts/openapi.yaml`.
- **Docs:** listed in section 6.

## 4. Migrations

| Revision | What | Phase |
|---|---|---|
| `0042` | `prescription_uploads` (platform data owned by a patient account, with CHECKs per state) and `ck_jobs_system_kind` extended with `process_prescription_upload` and `purge_prescription_uploads` | M7b-P6 |

M7a needs no migration: conversations are not stored and proposals are single-use through the
existing rate-limit table. Clinic logos, deferred (D5), have no migration. `0042` is expand-only;
its downgrade is tested (`test_0042_prescription_uploads_checks_and_round_trip`), and
`test_models_match_migrations` passes with the new table. Migrations run only through the
one-off `migrate` service, never at start-up.

## 5. ADRs

| ADR | Title | State |
|---|---|---|
| 0023 | The printed verification code and verified uploads (uploads are pointers, never sources) | Accepted |
| 0024 | Assistant turns, signed confirmations and guard rails | Accepted |

ADR-0013 (the LLM gateway) is unchanged and implemented. No accepted ADR was edited.

## 6. PRD, specs and documentation

- **PRD v1.3** (§0.0 C15, C16; §8.15 FR-AI-04, FR-RX-11, FR-UPL-01..05; §9 NFR-20; §13 rows for M7a
  and M7b). Landing-page polish moved to the backlog because the approved M7 structure omits it.
- **Specs:** `docs/specs/assistant.md` and `docs/specs/prescription-uploads.md` (new, implemented);
  `docs/specs/prescriptions.md` (layout 3).
- **Updated:** `docs/milestones/M7-assistant-and-verified-uploads.md` (plan and as-built record for
  both parts), `docs/milestones/M7-architecture-review.md` (moved from the repo root),
  `docs/ARCHITECTURE.md` (containers), `docs/DATA_MODEL.md`, `docs/API.md`, `docs/ERRORS.md` (the
  `AI_` and `UPL_` sections and prefixes), `docs/RUNBOOK.md` (33 the assistant's model, 34
  uploads and ClamAV, and the Contents entries), `docs/SECURITY_AND_COMPLIANCE.md` (§3 upload
  controls, §4 the M7 privacy review), `docs/DEBUG_JOURNAL.md` (#30, the e2e set-up during clinic
  hours), `docs/adr/README.md`, `AGENTS.md` (commands), `TASKS.md`, `NEXT_STEPS_PLAN.md`,
  `CHANGELOG.md`, `apps/web/e2e/README.md`, `.env.example`.

## 7. API

Contract `0.49.0` → `0.51.0` (0.50.0 for M7a, 0.51.0 for M7b), with web types regenerated and
`make contract-check` green.

| Method | Path | Who |
|---|---|---|
| POST | `/api/v1/portal/assistant/turns` | `@patient` |
| POST | `/api/v1/portal/assistant/confirm` | `@patient` |
| POST | `/api/v1/assistant/turns` | `@clinic(APPOINTMENTS_MANAGE)` |
| POST | `/api/v1/assistant/confirm` | `@clinic(APPOINTMENTS_MANAGE)` |
| POST | `/api/v1/portal/prescription-uploads` | `@patient` (multipart, 202) |
| POST | `/api/v1/portal/prescription-uploads/by-code` | `@patient` (201) |
| GET | `/api/v1/portal/prescription-uploads/{upload_id}` | `@patient` |
| POST | `/api/v1/portal/prescription-uploads/{upload_id}/challenge` | `@patient`, verified email |
| POST | `/api/v1/portal/prescription-uploads/{upload_id}/selection` | `@patient` |
| DELETE | `/api/v1/portal/prescription-uploads/{upload_id}` | `@patient` (204) |

New error codes: `AI_UNAVAILABLE`, `AI_PROVIDER_BUSY`, `AI_RATE_LIMITED`, `AI_PROPOSAL_INVALID`,
`AI_PROPOSAL_USED`; `UPL_FILE_REJECTED`, `UPL_RATE_LIMITED`, `UPL_TOO_MANY`, `UPL_UPLOAD_FAILED`,
`UPL_CHALLENGE_FAILED`, `UPL_NOT_AWAITING`, `UPL_NOT_VERIFIED`, `UPL_SELECTION_REQUIRED`, plus ten
rejection codes on an upload (`docs/ERRORS.md`). New settings: `LLM_*`, `WORKER_QUEUE`,
`CLAMD_HOST`, `CLAMD_PORT`, `CLAMD_TIMEOUT_SECONDS`. Every route has a declared access policy
(`test_access`), and every `@patient` route taking an ID has a cross-account case
(`test_portal_scope`).

## 8. Frontend

- `/portal/assistant`: the prescription picker for linked records (D7), the chat with the
  confirmation card, and the upload card for anything else: a photo or PDF, or the printed code;
  progress while the file is checked; the last-4 form with attempts left for someone else's
  prescription; for an older version, a choice between "the one I uploaded" and "the latest",
  never made for the user (D3); the privacy note (file deleted after the check, never seen by
  staff); *Remove*. English and Hindi. Home links to it (no sixth tab, which would overflow at
  360 px).
- `/assistant` in every clinic workspace (the staff assistant).
- Route handlers that answer oversized uploads and imports with the API's 413 (#30).
- Accessibility: axe clean on the assistant page with the upload card at 360 px (journeys 1, 2);
  no horizontal scroll.

## 9. Security decisions

- **The file is never a source of clinical content** (ADR-0023). The reader returns IDs and
  methods only; the assistant gets the chosen version's database page; an import-linter contract
  keeps the assistant and the LLM adapters away from upload intake, processing, scanning,
  extraction and storage.
- **Malware scanning before parsing**, on a separate worker; an unreachable scanner is retried
  and then rejects the upload, never passes it.
- **Limits:** type by first bytes, 10 MB (request capped before parsing on both origins), 40
  megapixels checked from the image header, 50 pages, 2 read; hourly limits per account and
  caller; 3 in flight per account.
- **No existence oracle:** any code outside the account's own records answers `NEEDS_CHALLENGE`;
  every challenge failure answers the same, from the upload's own count; the check reuses the
  prescription link's last-4 rule and lockout.
- **Representatives** get that one prescription chain for 24 hours and no portal link (D7).
- **QR payload** `MEDIEASE-RX:1:<uuid>`, no HMAC (D2): the ID grants nothing by itself.
- **Assistant:** stateless turns, no tool results from the client, writes as signed single-use
  proposals (10 minutes), advice requests referred before the model, ungrounded numbers replaced;
  the console model by default; a real provider refused in staging and production until
  `LLM_PATIENT_DATA_ALLOWED=true` after the provider contract and privacy review.
- **Tenancy:** `prescription_uploads` and the IDs-only prescription lookup are reviewed exceptions
  recorded in `tests/tenancy/test_repository_scoping.py`.
- **Containers:** `upload-worker` is hardened like the other app containers (non-root, read-only
  root, no capabilities; checked by `make smoke`). `clamav` keeps its image defaults, like `db`,
  and publishes clamd on `127.0.0.1` only.

## 10. Tests added

- **API:** domain tests for the upload state machine, guard rails (31 advice and 17 restating
  questions, English and Hindi), explanation and proposals, verification codes; adapter tests for
  the reader (real layout-3 PDFs and QR images) and a socket-level clamd fake, and for the LLM
  adapters; 26 assistant HTTP tests; 24 upload HTTP tests; contract tests for both; the 0042
  migration test; tenancy and portal-scope cases; the live ClamAV tests (EICAR, an EICAR PDF
  through the real processing job).
- **The mandatory boundary test** (`test_nfr_20_an_edited_document_with_a_genuine_qr_gives_the_model_only_the_database_record`,
  for a PDF and a photo): a layout-3 PDF rendered with the medicine changed to a sentinel, 900 mg
  and 90 days, keeping the genuine ID and QR, is uploaded, verified, and the scripted model's
  entire input contains the database lines (*Syrup X*, *5 ml*) and none of the edited text.
- **Issue #30 regression:** six proxy tests (declared and streamed oversize, pass-through,
  Retry-After, unreachable API, the import path) and a smoke check.
- **Web:** assistant and upload component tests.
- **Playwright:** journey 1 and the staff journey (M7a); journeys 2-5 (M7b).

## 11. Full suite results

| Gate | Result |
|---|---|
| `make test-api` | **2522 passed**, 0 failed, 0 skipped (the live ClamAV tests ran); coverage **96.06%** (gate 90%); domain + application **95%** (gate 80%). Baseline on `main`: 2313 passed, 1 skipped, 95.17% |
| `make test-web` | **722 passed** in 86 files (baseline 711) |
| `make lint typecheck` | Green: ruff, ruff format, import-linter (**5 contracts kept**, one new), ESLint, mypy (434 files), tsc |
| `make contract-check` | Green (types match `openapi.yaml` 0.51.0) |
| `make smoke` | Green, including the new checks: `upload-worker` and `clamav` healthy, clamd reachable from the upload worker, an 11 MB upload through the web origin answered 413, the upload worker non-root, read-only and without capabilities |
| Issue #30 reproduction | 15 of 15 oversized uploads through `:3000` answered 413 on the new route (the plain rewrite path, for comparison, answered its auth 401) |

## 12. Playwright results

**Final: 51 of 51 passed** (`make e2e`'s Playwright image and command, 4.9 minutes) on a fresh
throwaway compose project (`mediease-e2e`, its own volumes, `make seed`), which is how CI starts.
The developer's stack was stopped for the run and brought back with its data; only the throwaway
project's volumes were removed.

The M7 journeys, also run on their own on the developer's stack (all passing):

| Journey | Spec | Result |
|---|---|---|
| 1. The patient assistant explains a chosen prescription (and refers an advice question) | `assistant.spec.ts` | Pass |
| Staff assistant shows today's queue | `assistant.spec.ts` | Pass |
| 2. A family member uploads a valid prescription; ClamAV, QR, last-4 check; the assistant answers from the database | `uploads.spec.ts` | Pass |
| 3. An older version: historical or latest chosen by the user; the assistant follows each choice | `uploads.spec.ts` | Pass |
| 4. Another account's upload is 404 for reading and for the assistant; the code alone grants nothing | `uploads.spec.ts` | Pass |
| 5. An EICAR PDF is rejected by ClamAV, a QR-less image by the reader, a text file by type; files deleted, the forms return | `uploads.spec.ts` | Pass |

The earlier full runs on the long-lived local database, recorded for completeness:

- **11:30 IST: 27 of 51.** Every failure was set-up: the seeded 10:00-13:00 session was full from
  the day's runs, so `sessionRunningNow` could not add a session (`SCH_OVERLAP`). Not product
  code; the helper now says so (DEBUG_JOURNAL 2026-10-27).
- **13:02 IST: 47 of 51.** Two `workspaces` journeys still expected the menus without the M7a
  *Assistant* link (fixed in `b5d735b`); two booking journeys failed in `lonelySession` ("no free
  evening") with 65 leftover one-place sessions in the local database, the same local-only
  limitation recorded at the end of M6b and M6c.

## 13. Pre-existing failures and warnings

- No pre-existing test failures: the baseline on `main` was green and stays green.
- Three warnings, the same as the baseline: WeasyPrint's HarfBuzz-Subset deprecation notice, and
  two Alembic notes that index expressions with `text_pattern_ops` cannot be compared.
- The e2e helper `sessionRunningNow` depends on the time of day: during 10:00-13:00 IST, once
  earlier runs have filled the seeded session, journeys cannot set up (`SCH_OVERLAP`). Found in
  this milestone's full run; the helper now says so plainly (DEBUG_JOURNAL 2026-10-27). The
  permanent fix is backlog (section 14).
- The booking journeys' `lonelySession` helper fails on a long-lived local database once it has
  no free hour left among earlier runs' one-place sessions (recorded at the end of M6b and M6c
  too); a fresh stack, as in CI, passes.
- The `workspaces` journeys still expected the menus without M7a's *Assistant* link, because
  M7a ran only its own journeys; caught by this full run and fixed (`b5d735b`).
- Vitest occasionally times out starting a worker on the `/mnt/e` mount under load; a rerun
  passes (environmental, seen once).

## 14. Deferred work and known limits

- **Clinic logos** (D5): no upload, no migration, no layout change. The MediEase mark on layout 3
  is a placeholder until the official logo arrives (`assets/SOURCES.md`).
- **OCR** (D4): not built. A photo is read by its QR; without one the user types the code.
- **Landing-page polish:** backlog (PRD C15).
- **Patient cancel and reschedule by the assistant:** no patient use case exists (FR-PRT-08);
  the assistant points to the clinic.
- **A real model provider** needs L-04 and L-10 and `LLM_PATIENT_DATA_ALLOWED=true`.
- **A representative needs the prescription's link to exist**, because the last-4 check runs
  against it (RUNBOOK 34).
- **#30 for other upload paths:** visit attachments and certificates still use the plain rewrite;
  move them to `proxyWithLimit` when they get browser uploads at scale.
- **Per-caller limits** share the web server's address until a trusted proxy forwards the client's
  (ARCHITECTURE A11, existing).
- **Production:** ClamAV (about 1.5 GB of memory) and the `uploads/` prefix need the M9
  deployment design; S3 lifecycle rules can back up the sweep.
- **e2e independence from the time of day:** give the journeys their own doctor or a
  high-capacity seeded session.

## 15. Git status

Branch `m7/65-assistant-and-verified-uploads`, 20 commits ahead of `origin/main` with this
report, no upstream (never pushed). `main` untouched. No force push, no amend of pushed history,
no merge.

## 16. Working tree

Clean after the report's commit (`git status --short` prints nothing). Scratch files live in
`.exports/`, which is gitignored.

## 17. The AI-to-database boundary is enforced

Confirmed. The only path from an upload to the assistant is `ReadVerifiedUpload`, which reads
the chosen version from the clinic's tables through the account's scope or the verified chain;
the upload row holds IDs only and the file is gone by then. The import contract "the assistant
never reads an uploaded file" is kept, and the boundary test above proves the model sees the
database text and not the edited file's.

## 18. Uploads are not exposed to staff

Confirmed. No staff route lists, reads or serves an upload (`test_access` would fail on a new
route; `test_d6_no_staff_route_serves_or_lists_an_upload`); there is no staff screen; even the
account itself cannot download its file back. The only trace a clinic sees is the audit row
*Patient verified a prescription in the patient app* (IDs only).

## 19. Uploads are deleted

Confirmed. The file is deleted before the state that ends extraction or rejects the upload is
committed (tests assert an empty `uploads/` prefix after verification, every rejection, a
withdrawal and the sweep); abandoned uploads go after 1 hour, pending checks after 24 hours, rows
after 30 days. Verified on the live stack in journeys 2-5 and the live ClamAV test.

## 20. No OCR

Confirmed. No OCR library or model is installed or called. The reader decodes QR symbols
(zxing-cpp) and searches a PDF's own text layer for the exact code grammar; nothing else.

## 21. Clinic logos are deferred

Confirmed (D5). No logo upload, storage, migration or template change was made.

## Next steps for the developer

1. Review this report and the branch.
2. Give permission to push; I will push `m7/65-assistant-and-verified-uploads` with `-u` and open
   the milestone PR (summary, tests, and the deferred items above).
3. After CI is green, review and merge (I never merge).

## Appendix: changed files against `origin/main`

| Change | File |
|---|---|
| Modified | `.env.example` |
| Modified | `AGENTS.md` |
| Modified | `CHANGELOG.md` |
| Modified | `NEXT_STEPS_PLAN.md` |
| Modified | `TASKS.md` |
| Added | `apps/api/migrations/versions/0042_prescription_uploads.py` |
| Modified | `apps/api/pyproject.toml` |
| Modified | `apps/api/src/mediease_api/adapters/db/jobs.py` |
| Modified | `apps/api/src/mediease_api/adapters/db/models/__init__.py` |
| Added | `apps/api/src/mediease_api/adapters/db/models/uploads.py` |
| Modified | `apps/api/src/mediease_api/adapters/db/unit_of_work.py` |
| Added | `apps/api/src/mediease_api/adapters/db/uploads.py` |
| Added | `apps/api/src/mediease_api/adapters/extraction/__init__.py` |
| Added | `apps/api/src/mediease_api/adapters/extraction/identifier.py` |
| Added | `apps/api/src/mediease_api/adapters/llm/__init__.py` |
| Added | `apps/api/src/mediease_api/adapters/llm/console.py` |
| Added | `apps/api/src/mediease_api/adapters/llm/openai_compatible.py` |
| Added | `apps/api/src/mediease_api/adapters/malware/__init__.py` |
| Added | `apps/api/src/mediease_api/adapters/malware/clamd.py` |
| Modified | `apps/api/src/mediease_api/adapters/pdf/assets/SOURCES.md` |
| Added | `apps/api/src/mediease_api/adapters/pdf/assets/mediease-mark.svg` |
| Added | `apps/api/src/mediease_api/adapters/pdf/assets/page-3.css.j2` |
| Added | `apps/api/src/mediease_api/adapters/pdf/assets/prescription-3.css` |
| Added | `apps/api/src/mediease_api/adapters/pdf/assets/prescription-3.html.j2` |
| Modified | `apps/api/src/mediease_api/adapters/pdf/weasy.py` |
| Added | `apps/api/src/mediease_api/adapters/security/proposal_signer.py` |
| Added | `apps/api/src/mediease_api/application/assistant/__init__.py` |
| Added | `apps/api/src/mediease_api/application/assistant/engine.py` |
| Added | `apps/api/src/mediease_api/application/assistant/errors.py` |
| Added | `apps/api/src/mediease_api/application/assistant/patient.py` |
| Added | `apps/api/src/mediease_api/application/assistant/staff.py` |
| Added | `apps/api/src/mediease_api/application/assistant/tools.py` |
| Modified | `apps/api/src/mediease_api/application/portal/records.py` |
| Added | `apps/api/src/mediease_api/application/uploads/__init__.py` |
| Added | `apps/api/src/mediease_api/application/uploads/assistant.py` |
| Added | `apps/api/src/mediease_api/application/uploads/intake.py` |
| Added | `apps/api/src/mediease_api/application/uploads/processing.py` |
| Added | `apps/api/src/mediease_api/application/uploads/verify.py` |
| Modified | `apps/api/src/mediease_api/bootstrap.py` |
| Modified | `apps/api/src/mediease_api/config/settings.py` |
| Modified | `apps/api/src/mediease_api/delivery/errors.py` |
| Added | `apps/api/src/mediease_api/delivery/http/assistant.py` |
| Added | `apps/api/src/mediease_api/delivery/http/prescription_uploads.py` |
| Added | `apps/api/src/mediease_api/domain/assistant/__init__.py` |
| Added | `apps/api/src/mediease_api/domain/assistant/explain.py` |
| Added | `apps/api/src/mediease_api/domain/assistant/guard_rails.py` |
| Added | `apps/api/src/mediease_api/domain/assistant/llm.py` |
| Added | `apps/api/src/mediease_api/domain/assistant/proposal.py` |
| Modified | `apps/api/src/mediease_api/domain/audit/actions.py` |
| Modified | `apps/api/src/mediease_api/domain/audit/catalogue.py` |
| Modified | `apps/api/src/mediease_api/domain/jobs/job.py` |
| Modified | `apps/api/src/mediease_api/domain/jobs/schedule.py` |
| Modified | `apps/api/src/mediease_api/domain/prescriptions/document.py` |
| Modified | `apps/api/src/mediease_api/domain/prescriptions/patient_view.py` |
| Modified | `apps/api/src/mediease_api/domain/prescriptions/phrasebook.py` |
| Modified | `apps/api/src/mediease_api/domain/prescriptions/prescription.py` |
| Added | `apps/api/src/mediease_api/domain/prescriptions/verification.py` |
| Added | `apps/api/src/mediease_api/domain/uploads/__init__.py` |
| Added | `apps/api/src/mediease_api/domain/uploads/checks.py` |
| Added | `apps/api/src/mediease_api/domain/uploads/errors.py` |
| Added | `apps/api/src/mediease_api/domain/uploads/upload.py` |
| Added | `apps/api/src/mediease_api/ports/assistant.py` |
| Added | `apps/api/src/mediease_api/ports/llm.py` |
| Modified | `apps/api/src/mediease_api/ports/unit_of_work.py` |
| Added | `apps/api/src/mediease_api/ports/uploads.py` |
| Added | `apps/api/tests/assistant_helpers.py` |
| Added | `apps/api/tests/contract/test_assistant_contract.py` |
| Added | `apps/api/tests/contract/test_prescription_uploads_contract.py` |
| Modified | `apps/api/tests/integration/db/test_migrations.py` |
| Added | `apps/api/tests/integration/test_assistant_http.py` |
| Added | `apps/api/tests/integration/test_clamd_live.py` |
| Added | `apps/api/tests/integration/test_prescription_uploads_http.py` |
| Modified | `apps/api/tests/tenancy/test_portal_scope.py` |
| Modified | `apps/api/tests/tenancy/test_repository_scoping.py` |
| Added | `apps/api/tests/unit/adapters/test_llm_adapters.py` |
| Modified | `apps/api/tests/unit/adapters/test_pdf_renderer.py` |
| Added | `apps/api/tests/unit/adapters/test_upload_adapters.py` |
| Added | `apps/api/tests/unit/application/test_assistant_tools.py` |
| Modified | `apps/api/tests/unit/delivery/test_access.py` |
| Added | `apps/api/tests/unit/domain/test_assistant_explain_and_proposal.py` |
| Added | `apps/api/tests/unit/domain/test_assistant_guard_rails.py` |
| Modified | `apps/api/tests/unit/domain/test_patient_view.py` |
| Added | `apps/api/tests/unit/domain/test_rx_verification.py` |
| Added | `apps/api/tests/unit/domain/test_uploads.py` |
| Added | `apps/api/tests/upload_helpers.py` |
| Modified | `apps/web/e2e/README.md` |
| Added | `apps/web/e2e/assistant.spec.ts` |
| Modified | `apps/web/e2e/portal-support.ts` |
| Modified | `apps/web/e2e/queue-support.ts` |
| Added | `apps/web/e2e/upload-support.ts` |
| Added | `apps/web/e2e/uploads.spec.ts` |
| Modified | `apps/web/e2e/workspaces.spec.ts` |
| Added | `apps/web/src/app/(clinic)/(workspace)/assistant/page.tsx` |
| Added | `apps/web/src/app/(patient)/portal/(app)/assistant/page.tsx` |
| Added | `apps/web/src/app/api/v1/ops/clinics/[clinicId]/patient-imports/route.ts` |
| Added | `apps/web/src/app/api/v1/portal/prescription-uploads/route.ts` |
| Added | `apps/web/src/features/assistant/Chat.tsx` |
| Added | `apps/web/src/features/assistant/PortalAssistant.tsx` |
| Added | `apps/web/src/features/assistant/StaffAssistant.tsx` |
| Added | `apps/web/src/features/assistant/UploadPanel.tsx` |
| Added | `apps/web/src/features/assistant/assistant.test.tsx` |
| Added | `apps/web/src/features/assistant/uploads.test.tsx` |
| Modified | `apps/web/src/features/portal/Home.tsx` |
| Modified | `apps/web/src/features/shell/nav.test.ts` |
| Modified | `apps/web/src/features/shell/workspace.ts` |
| Modified | `apps/web/src/lib/api/client.ts` |
| Added | `apps/web/src/lib/api/limited-proxy.test.ts` |
| Added | `apps/web/src/lib/api/limited-proxy.ts` |
| Modified | `apps/web/src/lib/api/schema.d.ts` |
| Modified | `apps/web/src/lib/auth/portal-session.ts` |
| Modified | `apps/web/src/lib/i18n/portal.ts` |
| Modified | `contracts/openapi.yaml` |
| Modified | `docker-compose.yml` |
| Modified | `docs/API.md` |
| Modified | `docs/ARCHITECTURE.md` |
| Modified | `docs/DATA_MODEL.md` |
| Modified | `docs/DEBUG_JOURNAL.md` |
| Modified | `docs/ERRORS.md` |
| Modified | `docs/PRD.md` |
| Modified | `docs/RUNBOOK.md` |
| Modified | `docs/SECURITY_AND_COMPLIANCE.md` |
| Added | `docs/adr/0023-printed-verification-code-and-verified-uploads.md` |
| Added | `docs/adr/0024-assistant-turns-confirmations-and-guard-rails.md` |
| Modified | `docs/adr/README.md` |
| Added | `docs/milestones/M7-architecture-review.md` |
| Added | `docs/milestones/M7-assistant-and-verified-uploads.md` |
| Added | `docs/specs/assistant.md` |
| Added | `docs/specs/prescription-uploads.md` |
| Modified | `docs/specs/prescriptions.md` |
| Modified | `scripts/smoke.sh` |

Plus this report (added).
