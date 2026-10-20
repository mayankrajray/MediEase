# MediEase — Debug Journal

A running record of real bugs: what we saw, why it happened, how we fixed it, and what stops it
coming back. Search this file **before** debugging — the same failure may already be solved.

Rules:

- One entry per root cause, newest first.
- No patient data, real phone numbers or clinical content — use IDs and codes.
- Link the fixing commit and the test that now guards it.
- If the lesson is general, also update `DEBUGGING.md` §4 or `RUNBOOK.md`.

## Entry template

```markdown
### YYYY-MM-DD — <short title> (`ERROR_CODE` if any)

- **Milestone / area:** M3 / appointments
- **Symptom:** What was observed, where, by whom. Include request_id(s).
- **Impact:** Who was affected and how badly (local only / staging / pilot clinic).
- **Reproduction:** Minimal steps or the failing test name.
- **Investigation:** Evidence looked at, hypotheses tried and discarded.
- **Root cause:** The actual reason, one or two sentences.
- **Fix:** What changed. Commit: `<sha>` — PR: #<n>
- **Guard:** Test(s) added: `tests/...::test_...`
- **Prevention / follow-up:** Docs updated, alerts added, patterns to avoid.
- **Search keywords:** timezone, midnight, session, IST
```

---

### 2026-10-20 — web tests timing out on a many-core machine (M6-P1, no error code)

- **Milestone / area:** M6-P1 / web test runner
- **Symptom:** `PrintAndLink.test.tsx` › "Print opens the tab at the click…" failed in every full
  `npx vitest run` (twice in a row) with `Unable to find role="button"`: the DOM was still at
  "Loading Alpha Clinic…". The same file passed alone, in 233 ms.
- **Impact:** Local only. The same test had timed out under load once before (M5-P2 notes).
- **Reproduction:** a full web run on a 20-core WSL machine with Vitest's default workers.
- **Investigation:** the failing render had taken 1,227 ms against Testing Library's 1 s wait.
  Other tests in that run also took about 1 s each. With `--maxWorkers=6` and with `50%` the suite
  passed twice, and it finished faster (about 15.5 s instead of 20 s). So the cause is CPU
  oversubscription, not the shell. M6-P1's heavier shell (Motion, the sidebar and the drawer)
  pushed a test that was already close to the limit over it.
- **Root cause:** one jsdom worker per core minus one oversubscribes the CPU, so the first
  workspace render in a file can take longer than the 1 s wait.
- **Fix:** `maxWorkers: "50%"` in `apps/web/vitest.config.mts`. No assertion or timeout changed.
- **Guard:** the full web suite in `make test`.
- **Prevention / follow-up:** if a `findBy…` times out only in full runs, check the worker count
  before raising any timeout.
- **Search keywords:** vitest, timeout, findByRole, workers, load, flaky, jsdom

---

### 2026-10-18 — a message Meta accepted and then reported failed could not be saved (M5-P3, no error code)

- **Milestone / area:** M5-P3 / messaging
- **Symptom:** `test_a_failed_status_records_the_mapped_code` failed with an `IntegrityError` on
  `ck_messages_sent_has_provider_id` when a `failed` status arrived for a `SENT` message.
- **Impact:** Local only, before commit. With Meta, every delivery failure reported later
  (`131026` usually arrives this way) would have made the processing job fail until it went
  `dead`, leaving the message shown as `SENT`.
- **Reproduction:** send a message, then process a webhook with `"status": "failed"` for it.
- **Investigation:** the update set `FAILED` and kept `sent_at` and `provider_message_id`; the CHECK
  from `0015` said "accepted **if and only if** those are set".
- **Root cause:** the P2 CHECK assumed a failed message was never accepted, which is true for a
  synchronous refusal but not for a delivery failure reported later.
- **Fix:** migration `0016` makes the CHECK one-way (accepted ⇒ provider ID and send time).
- **Guard:** `tests/integration/test_webhooks_http.py::test_a_failed_status_records_the_mapped_code`.
- **Prevention / follow-up:** state CHECKs as implications unless the converse is a real rule.
- **Search keywords:** ck_messages_sent_has_provider_id, failed status, webhook, IntegrityError

---

### 2026-10-18 — a restarted worker reused console message IDs, so a "sent" message ended `MSG_OUTCOME_UNKNOWN` (M5-P2)

- **Milestone / area:** M5-P2 / messaging
- **Symptom:** On the stack, after `docker compose stop worker` / `start worker`, the next
  `send_rx_link` logged `messaging.console_accepted`, then `job.handler_error` with
  `IntegrityError`; the retry found the row still started and failed it as `MSG_OUTCOME_UNKNOWN`.
- **Impact:** Local only, before commit. With a real provider the same class of failure (the
  outcome write failing after acceptance) is handled the same way, by design (decision 4A).
- **Reproduction:** send one message, restart the worker, send another.
- **Investigation:** the failing statement was the outcome update: `uq_messages_provider_message_id`.
  Both rows had `console-00000001`.
- **Root cause:** the console adapter numbered IDs from a per-process counter; the column is unique
  across all messages (for P3's webhooks). The integration tests' scripted provider built IDs from
  the idempotency key, so they never repeated.
- **Fix:** console IDs are `console-<uuid4 hex>`.
- **Guard:** `tests/unit/adapters/test_messaging_adapters.py::test_the_console_provider_logs_names_not_values_and_repeats_its_answer`
  (two adapters never give the same ID).
- **Prevention / follow-up:** a fake provider's IDs must be unique like a real one's; the
  at-most-once rule worked as intended (no second send).
- **Search keywords:** console adapter, provider_message_id, unique, worker restart, outcome unknown

---

### 2026-10-18 — `enqueue` reported "already queued" for every new job (M5-P1, no error code)

- **Milestone / area:** M5-P1 / jobs
- **Symptom:** In the first run of the job tests, `uow.jobs.enqueue(job)` returned `False` for a job
  that did not exist yet, and 17 database tests failed.
- **Impact:** Local only, before the first commit; it would have made every enqueue look like a
  duplicate and the caller skip its work.
- **Reproduction:** `tests/integration/test_jobs_db.py::test_r9c_a_job_exists_only_if_the_change_that_enqueued_it_committed`.
- **Investigation:** The row was inserted, so `ON CONFLICT DO NOTHING` was not firing. The return
  value was `session.execute(insert(JobRow)....on_conflict_do_nothing(...)).rowcount == 1`.
- **Root cause:** `rowcount` of an ORM-enabled `INSERT … ON CONFLICT` is not reliable (the insert
  can be batched, and the driver then reports -1), so "1 row" was never true.
- **Fix:** Add `RETURNING id` and treat "a row came back" as "added". Commit: the M5-P1 jobs commit — PR: the M5 milestone PR (#40 is its issue).
- **Guard:** The enqueue tests in `tests/integration/test_jobs_db.py` (a duplicate live key returns
  `False`, a new key `True`, a cancelled or dead key `True`).
- **Prevention / follow-up:** Do not use `rowcount` to learn whether an ORM insert did anything;
  use `RETURNING`. (It is fine for the `UPDATE`/`DELETE` statements in the job store, whose tests
  prove the counts.)
- **Search keywords:** rowcount, on_conflict_do_nothing, RETURNING, enqueue, dedupe, outbox

### 2026-10-18 — a failure type that is a frozen dataclass cannot be raised (M5-P1, caught while writing, before it ran)

- **Milestone / area:** M5-P1 / domain jobs
- **Symptom:** `JobFailure` was first written as `@dataclass(frozen=True)` subclassing `Exception`.
- **Impact:** None in the repository; it would have raised `FrozenInstanceError` the first time a
  handler raised it.
- **Root cause:** Python sets `__traceback__` (and `__context__`) on an exception when it is
  raised, and a frozen dataclass refuses attribute assignment.
- **Fix:** A plain `Exception` subclass with `code` and `retryable` set in `__init__`.
- **Guard:** `tests/unit/domain/test_jobs.py::test_a_job_failure_can_be_raised_and_carries_its_code`.
- **Search keywords:** frozen dataclass, Exception, FrozenInstanceError, raise
## Entries

### 2026-10-18 — Hindi prescription PDFs lost spaces between some words

- **Milestone / area:** M4-P4 / PDF renderer
- **Symptom:** A rendered Hindi PDF, viewed as an image, showed "खोलने के7 दिन" and a footer
  "MediEase द्वाराडिजिटल रूप सेतैयार". All tests passed: they read text back from the PDF, and
  extraction does not show word gaps reliably.
- **Impact:** Local only, before the phase was confirmed. Patients would have received Hindi
  prescriptions with joined words.
- **Reproduction:** Render a Hindi prescription and look at the page (not the extracted text).
- **Investigation:** Rendering the same strings with each family order showed the body fault
  only with Noto Sans (Latin) first. The footer still failed with Devanagari first; its text is a
  CSS `content` string, and our escaping writes `\00094d`-style escapes with no terminator.
- **Root cause:** Two: with Latin first, a space after a Devanagari vowel sign was laid out from
  the Latin face and collapsed; and CSS consumes one whitespace after a hex escape, so the real
  space after an escaped vowel sign vanished.
- **Fix:** The print stylesheet puts the prescription's own script first; each CSS escape ends
  with its own space. Commit: `241bc12` — PR: #39
- **Guard:** `tests/unit/adapters/test_pdf_renderer.py::test_css_strings_keep_the_space_after_an_escaped_character`
  and `::test_the_prescriptions_own_script_takes_the_first_font`.
- **Prevention / follow-up:** Look at a rendered page of every new layout in both languages;
  text extraction is not proof of what a patient sees. The Hindi wording itself still awaits a
  clinician's review (L-07).
- **Search keywords:** Devanagari, Hindi, PDF, WeasyPrint, space, matra, CSS escape, font order

### 2026-10-18 — The booking drawer's patient search lost the focus in CI after a jsdom bump

- **Milestone / area:** M3-P5 web (found on the M4 PR, #39) / modals, focus
- **Symptom:** CI's web job failed on every M4 push from `ce61ec7`:
  `Booking.test.tsx` "AC6 … two interactions in the drawer", `expect(…"Patient").toHaveFocus()`.
  Locally the same suite passed again and again.
- **Impact:** CI only; `main`'s own run after the M3 merge (`c44ad49`) is red for the same
  reason. In a browser the search box could also open without the focus, which costs the front
  desk the first of its three interactions (AC6).
- **Reproduction:** `npm ci` in `apps/web` (jsdom 30.1.2 from the lockfile), then
  `npx vitest --run`; the WSL clone still had jsdom 30.1.1 installed, which is why it passed there.
- **Investigation:** Only the web job failed; the M4 branch changes no web code apart from
  generated types. Comparing installed versions with `package-lock.json` showed jsdom 30.1.1 vs
  30.1.2 and vitest 5.0.3 vs 5.0.4: Dependabot's bumps landed on `main` just before the M3 merge.
  After `npm ci` the failure reproduced every time. Which jsdom change causes it was not traced.
- **Root cause:** `PatientPicker` focused its input in its own effect, which React runs before
  the parent `Drawer` effect that opens the `<dialog>`; that early `focus()` does not stick under
  jsdom 30.1.2 (and is fragile in browsers, where `showModal()` moves the focus itself).
- **Fix:** `Drawer` and `Dialog` focus a descendant marked `data-autofocus` once the dialog is
  open; the patient search carries it. A wizard test that read an accessible description one
  render early now waits for it. PR: #39.
- **Guard:** `components/Modal.test.tsx` (a `data-autofocus` field has the focus once a Drawer or
  Dialog is open); the AC6 booking test.
- **Prevention / follow-up:** Run web tests after `npm ci` (as CI does) whenever the lockfile
  changes on `main`, not against an older `node_modules`. In modals, set the starting focus with
  `data-autofocus`, not from the child's own effect.
- **Search keywords:** toHaveFocus, focus, dialog, showModal, Drawer, jsdom 30.1.2, Dependabot,
  npm ci, CI only
### 2026-10-17 — Sign-in failed with "Something went wrong" over plain HTTP on a non-localhost host

- **Milestone / area:** M2-P5 / web API client (found by the first CI Playwright run)
- **Symptom:** The CI `smoke` job's journey stayed on `/sign-in` with "Something went wrong. Please
  try again." and no Ref. Locally, through `http://localhost:3000`, the same spec passed.
- **Impact:** CI only, before merge. It would hit anyone opening the app over HTTP by any name or
  address other than localhost (a LAN address, an HTTP-only staging host). Production uses TLS.
- **Reproduction:** Playwright against `http://web:3000` (the compose network, as `make e2e` does),
  or locally with Chromium's `--host-resolver-rules=MAP web 127.0.0.1` and the old web image.
- **Investigation:** The message is `describeError`'s text for an error that is not an `ApiError`,
  so the failure was in the browser before any request. `newRequestId()` called
  `crypto.randomUUID()`, which browsers expose only in secure contexts (HTTPS, localhost);
  `http://web:3000` is not one, so every API call threw a `TypeError`.
- **Root cause:** A secure-context-only browser API on the path of every request.
- **Fix:** `newRequestId()` falls back to an RFC 4122 v4 UUID built from `crypto.getRandomValues`,
  which works in every context.
- **Guard:** `client.test.ts` "newRequestId" (works without `randomUUID`); the Playwright journey
  runs at `http://web:3000` in CI.
- **Prevention / follow-up:** Browser APIs on the request path must work outside secure contexts,
  or be checked first. Keep the e2e base URL a non-localhost name so CI catches this class of bug.
- **Search keywords:** randomUUID, secure context, crypto, sign-in fails, something went wrong, http, e2e
### 2026-10-03 — Secrets scan failed on `main` after the M1 rebase merge

- **Milestone / area:** M1 → M2 / CI, gitleaks
- **Symptom:** The CI "Secrets scan" job (`gitleaks (full history)`) reported `leaks found: 1` on
  the `main` push after PR #20 merged, on the first M2 pushes (PR #22), and later on every
  Dependabot PR based on `main`.
- **Impact:** CI only; no secret involved. `main` and Dependabot PRs show a red check.
- **Reproduction:** On a clone of `main`, run the pinned image from `ci.yml`:
  `docker run --rm -v "$PWD:/repo:ro" ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd… git /repo --redact --no-banner --exit-code 1`.
- **Investigation:** The finding is
  `1324cff…:apps/api/tests/conftest.py:generic-api-key:230`, the synthetic test password reviewed
  as a false positive in M1-P2 (`8a270d8`). `.gitleaksignore` on `main` names the same line at
  `244905a`, its SHA on the M1 branch.
- **Root cause:** gitleaks fingerprints include the commit SHA. Rebase-merging PR #20 gave the
  commit a new SHA on `main` (`1324cff`), so the reviewed fingerprint stopped matching.
- **Fix:** `b994ed3` adds the `1324cff` fingerprint (and keeps the old one). It is on
  `m2/21-patients` and reaches `main` with PR #22. Verified 17 Oct 2026 with the pinned image:
  `main` alone reports 1 leak; `main` with the M2 `.gitleaksignore` reports none.
- **Guard:** the CI Secrets scan job.
- **Prevention / follow-up:** For a new false positive, prefer an inline `gitleaks:allow` (it
  survives rebases) over a SHA fingerprint; after a rebase merge, re-run the scan on `main` and
  re-point any branch fingerprints. The `1324cff` entry is now stable because that commit is on
  `main`. Never widen the gitleaks rules instead.
- **Search keywords:** gitleaks, secrets scan, leaks found, fingerprint, rebase merge, SHA,
  gitleaksignore, Dependabot red

### 2026-10-03 — An API test run hung for half an hour (consent race test)

- **Milestone / area:** M2-P3 / tests, concurrency
- **Symptom:** `make test-api` stopped making progress and ran for about 30 minutes with no output.
- **Impact:** Local only, during M2-P3.
- **Reproduction:** A two-thread race test whose second thread is started only after the first
  finishes, with both waiting on a `threading.Barrier(2)` without a timeout.
- **Investigation:** The hang was in the new opt-out-versus-consent race test
  (`tests/integration/test_patient_consent_http.py`): the first thread waited at the barrier for a
  second thread that was never started until the first returned.
- **Root cause:** The test started its racing threads one after the other instead of together,
  and nothing bounded a wait in a test.
- **Fix:** The race test starts both threads before joining them (shipped with M2-P3, `958945b`).
  `3cf05cc` gives the barriers in both race tests a timeout, adds `pytest-timeout==2.4.0`
  (dev only, `timeout = 120`, `timeout_method = "thread"`, prints every thread's stack) and a
  `timeout-minutes` limit (5–20 minutes) to every CI job.
- **Guard:** `pytest-timeout` in `apps/api/pyproject.toml`; `timeout-minutes` in `ci.yml`.
- **Prevention / follow-up:** Race tests start every thread before any of them waits, and every
  barrier, join or queue wait in a test has a timeout.
- **Search keywords:** hang, hung, stuck, pytest, barrier, thread, race, timeout, deadlock

### 2026-10-03 — Accepting an invitation could replace an existing account's password (R13)

- **Milestone / area:** M1-P5 (found while building M1-P6) / invitations, security
- **Symptom:** Building the invitation page showed that accepting an invitation always set the
  password it was given, even when the invited email or phone already had an account.
- **Impact:** Local only, found before M1 merged. Whoever held an invite link for an existing
  account could take it over, including its memberships in other clinics.
- **Reproduction:** A user with a password in clinic A is invited to clinic B; accepting B's link
  with any new password succeeded and replaced theirs.
- **Investigation:** The accept use case had one path for new and existing accounts.
- **Root cause:** Acceptance treated the invitation token as proof of the account, but it only
  proves access to the link.
- **Fix:** For an existing account, acceptance needs that account's current password, never
  changes it, and shares the sign-in lockout (spec identity-and-tenancy R13, contract 0.5.1).
  Commits `047c0bb` (API) and `b5f2e9d` (web page asks for the current password).
- **Guard:** `tests/integration/test_onboarding_http.py::test_r13_the_invite_link_alone_cannot_take_over_an_existing_account`
  and the other `test_r13_*` tests there; `AcceptInviteForm.test.tsx`.
- **Prevention / follow-up:** A token that grants access to an account is reviewed for what it
  proves (the link) versus what it unlocks (the account).
- **Search keywords:** invitation, accept, takeover, password overwritten, existing account, R13

### 2026-10-02 — `/ready` took 4 s to report a stopped database (`READY_DB_UNAVAILABLE`)

- **Milestone / area:** M0-P3 / readiness, compose networking
- **Symptom:** With `docker compose stop db`, `/ready` returned the right 503
  `READY_DB_UNAVAILABLE` but after ~4.0 s on every call, outside the 2-second budget.
- **Impact:** Local only, caught before merge.
- **Reproduction:** `make up`, `docker compose stop db`, `curl -w '%{time_total}' localhost:8000/ready`.
- **Investigation:** Inside the `api` container, `socket.getaddrinfo("db", 5432)` alone took 4.03 s
  to fail; a direct psycopg connect with `connect_timeout=2` also took 4.0 s, so neither the pool
  nor the query was the cause. libpq's `connect_timeout` does not cover name resolution.
- **Root cause:** When a compose service is stopped, Docker's embedded DNS no longer knows its
  name and forwards the lookup upstream; with default resolver options the failure arrives after
  ~4 s (measured on Docker Desktop + WSL2).
- **Fix:** `dns_opt: [timeout:1, attempts:1]` on the `api` service. Lookup failure now takes
  ~2.0 s on the first call and ~1.0 s after. Commit: see PR for #10.
- **Guard:** Manual check in the M0-P3 verification steps (`time_total` with db stopped).
  Adapter-level timeouts are covered by `tests/integration/db/test_readiness_check.py`.
- **Prevention / follow-up:** Any service that probes another compose service by name inside a
  time budget needs the same resolver options. Revisit when production networking is chosen (M6).
- **Search keywords:** ready slow, 4 seconds, DNS, getaddrinfo, stopped container, dns_opt,
  connect_timeout, compose

### 2026-10-01 — WSL terminal crashes during the M0-P2 dependency install

- **Milestone / area:** M0-P2 / developer environment (Windows 11 + WSL2 + Docker Desktop)
- **Symptom:** The WSL terminal window closed three times in a row while installing the API's
  Python dependencies; the install never finished.
- **Impact:** Local only. Blocked M0-P2.
- **Reproduction:** Docker Desktop running for a few hours, then a `pip install` in WSL.
- **Investigation:** Windows Event Log showed Resource-Exhaustion-Detector event 2004 ("low
  virtual memory") once per attempt, followed by `wslservice.exe` faulting (event 1000), "WSL
  Service terminated unexpectedly" (event 7034) and a `dwm.exe` crash. The top consumer listed in
  event 2004 was `com.docker.backend.exe` at ~30.8 GB of committed memory on a 15.7 GB machine
  (commit charge 40 of 41.8 GB). Not a dependency problem: pip used prebuilt wheels throughout.
- **Root cause:** The Docker Desktop backend process (a Windows process, not the WSL VM) grows
  its committed memory over time until Windows runs out of virtual memory, at which point the WSL
  service is killed. No `%USERPROFILE%\.wslconfig` existed, so the WSL VM was uncapped as well.
- **Fix:** Added `%USERPROFILE%\.wslconfig` with `memory=8GB`, `processors=4`, `swap=8GB`
  (`swapFile` under the user profile — the drive root is not writable by WSL). Stopped Docker
  Desktop during the install: commit charge fell from 40 GB to 11 GB and the install completed.
  Added `make install-api` so the venv is created reproducibly with `--prefer-binary`.
- **Guard:** None automated — host configuration. Check `free -h` in WSL shows the cap.
- **Prevention / follow-up:** Quit Docker Desktop when it is not needed (M0-P2 needs no
  containers). Before M0-P3, update Docker Desktop and restart it fresh; if
  `com.docker.backend.exe` grows past a few GB again, report it upstream. Python 3.14 (Ubuntu
  26.04 default) is not the project interpreter — use 3.12 (ADR-0002).
- **Search keywords:** WSL crash, terminal closes, low virtual memory, event 2004, wslservice,
  vmmem, com.docker.backend, wslconfig, pip install
