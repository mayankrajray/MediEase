# MediEase — Testing Strategy

## 1. Test layers

| Layer | Tool | Location | What it proves | Speed |
|---|---|---|---|---|
| Domain unit | pytest | `apps/api/tests/unit/domain/` | Rules and state machines, no I/O | ms |
| Application unit | pytest + in-memory fakes of ports | `apps/api/tests/unit/application/` | Use cases orchestrate ports correctly | ms |
| Integration | pytest + real PostgreSQL (container) | `apps/api/tests/integration/` | Repositories, transactions, locks, migrations | s |
| Tenancy | pytest + real PostgreSQL | `apps/api/tests/tenancy/` | No endpoint leaks across clinics | s |
| Contract | schemathesis / openapi-core against `contracts/openapi.yaml` | `apps/api/tests/contract/` | API matches the published contract | s |
| Web unit | Vitest + Testing Library | `apps/web/src/**/*.test.tsx` | Components and hooks | ms |
| End-to-end | Playwright | `apps/web/e2e/` | Critical journeys through the real stack | min |
| Performance | k6 or Locust (M6) | `tests/perf/` | NFR-01, FR-PAT-04 targets | min |

Tool choices are confirmed and pinned in the milestone that introduces them.

## 2. Rules

- **Name the requirement.** `test_fr_rx_09_revision_supersedes_previous_version`.
- **Arrange with builders, not fixtures copied from reality.** `PatientBuilder().minor().build()`
  generates synthetic names and `+9190000000xx` numbers.
- **Freeze time through the clock port.** No test depends on the wall clock or the machine timezone.
  CI runs with `TZ=America/New_York` on purpose to flush out timezone assumptions.
- **Test failure paths.** Every use case has at least one test for invalid input, one for missing
  permission and, when tenant data is involved, one for cross-tenant access.
- **No network in tests.** Messaging uses the console/fake adapter; provider adapters have
  contract tests against recorded, scrubbed responses.
- **Each test cleans up.** Integration tests run inside a transaction that rolls back, or against a
  fresh schema per worker.
- **Flaky is broken.** A flaky test is fixed or quarantined with an issue the same day — never ignored.

## 3. Critical end-to-end journeys (must stay green from the milestone they arrive)

| Journey | From |
|---|---|
| Sign in → switch clinic → see today's queue | M1/M3 |
| Register patient with existing phone → choose existing (`e2e/patients-duplicate-phone.spec.ts`) | M2 |
| Book from the queue in ≤ 3 interactions (AC6, `e2e/booking-three-interactions.spec.ts`) | M3 |
| Two browsers on the queue: arrived on one shows on the other within one poll (AC4, `e2e/queue-two-browsers.spec.ts`) | M3 |
| Unchanged queue is a 304 through the web origin (R12, `e2e/live-queue-etag.spec.ts`) | M3 |

The M3 journeys add a session of the sample doctor running now (an extra session) and a fresh
synthetic patient through the API first (`e2e/queue-support.ts`), so they pass at any hour and
on a database that has been used before.
| Book slot → mark arrived → start consultation → issue Rx → print PDF (`e2e/consultation-keyboard.spec.ts`, at 1366 × 768, keyboard-only entry) | M4 |
| Open patient link on a 360-px viewport → wrong last-4 → correct last-4 → view Rx (`e2e/patient-link-360.spec.ts`) | M4 |
| Issue Rx with follow-up → reminder scheduled → worker sends via console adapter → status updates (`e2e/reminders-follow-ups.spec.ts`: the chip on the consultation and the profile, and the prescription link appearing in the message history once the worker sent it; the reminder's own send is due the day before, so its Scheduled → Sent change is checked on the stack and in `tests/integration/test_reminders_http.py`) | M5 |
| Pending follow-ups → Book follow-up → Confirm, on `make seed`'s overdue follow-up (`e2e/reminders-follow-ups.spec.ts`) | M5 |
| Ops open this month's messaging costs (`e2e/reminders-follow-ups.spec.ts`) | M5 |
| Patient replies STOP → opted out → next reminder skipped (API level: `tests/integration/test_opt_out_db.py`, AC5; the webhook needs the app secret to sign, so not in the browser journeys) | M5 |

## 4. Mandatory special suites

- **Tenancy suite** — for every endpoint: user of clinic A requests clinic B's resource → 404, and
  list endpoints never include clinic B rows.
- **Concurrency suite** — FR-APT-04 double booking with parallel requests; job claiming with two
  workers never processes one job twice.
- **Leakage suite** — run representative flows with log capture and assert no patient name,
  unmasked phone, or prescription text appears in logs or message variables.
- **Immutability suite** — issued prescriptions and audit events cannot be updated through the API
  or the application database role.

## 5. CI gates

A PR merges only when all pass:

1. Lint and format (Ruff, ESLint/Prettier)
2. Type checks (mypy, tsc)
3. Unit + integration + tenancy + contract tests
4. Import-boundary check (domain/application purity)
5. Build of all images
6. Dependency, image and secrets scanning
7. Coverage ≥ 80% on `domain/` and `application/` (NFR-14), plus ≥ 90% on the whole API package
   (`make test-api`, CI "API" job; from M1-P1)

End-to-end tests run on every PR from M2-P5: the CI `smoke` job seeds the stack and runs `make e2e`,
which runs Playwright (Chromium, 1366×768) in its official image on the compose network, so no
browser is installed on the host. Locally: `make up && make seed && make install-web && make e2e`;
the report and traces of a failure are in `apps/web/playwright-report/` and `test-results/`.
Nightly runs against staging start in M6.

**Incremental CI (from M7c, 11 Nov 2026).** A pull request runs only the jobs its changes can
affect; the `Detect changes` job lists the changed files against the PR's base and writes what runs,
and why, to the run's summary. The selection is by component, because the API and the web app meet
only through `contracts/openapi.yaml` and the compose stack:

| Changed | API | Web | Images | Stack and journeys |
|---|---|---|---|---|
| `apps/api/**` | ✓ | | ✓ | ✓ |
| `apps/web/**` except `e2e/` | | ✓ | ✓ | ✓ |
| `apps/web/e2e/**` | | | | ✓ |
| `contracts/**` | ✓ | ✓ | ✓ | ✓ |
| `docker-compose.yml`, `Makefile`, `.env.example`, `scripts/**` | | | | ✓ |
| `.github/**` | ✓ | ✓ | ✓ | ✓ |
| docs and other text | | | | |

`Config and contract` and `Secrets scan` always run. Inside a job nothing is skipped: when the API
is touched the whole API suite runs with its coverage gates, and the same for the web suite, because
a changed shared module can break a test whose files did not change. A push to `main`, the nightly
run (02:00 IST) and a manual run with *full* run every job. `CI result` is the one check to require:
it fails if any job that ran failed or was cancelled.

Caches (never test results): the API's virtual environment (key: Python patch version and
`pyproject.toml`), mypy's incremental cache, the PDF renderer's `.deb` packages (key: runner
image version, so the Ubuntu mirrors are used only when the image changes), the web's
`node_modules` (key: `.nvmrc` and `package-lock.json`) and the Next.js build cache. Bump the `-v1`
in a key to discard one.

Runners: `Detect changes`, `Config and contract` and `CI result` run on `ubuntu-slim` (a 1 vCPU
container, 15-minute cap, Docker CLI but no daemon). The other jobs need a full VM (Docker, or the
API suite's ~15 minutes) and are pinned to `ubuntu-24.04`. The API job runs inside the API image's
base (`python:3.12.15-slim-trixie`, same digest as `apps/api/Dockerfile`) and installs Pango,
HarfBuzz, fontconfig and tzdata from Debian: on 11 Nov 2026 every Ubuntu apt mirror was unreachable
from the runner host (noble and resolute alike). The system packages' cache key names the base
image digest; change both together.

The API suite runs in parallel (`pytest -n auto`, pytest-xdist, 4 processes on the runner): about 7
minutes instead of 13.5. Each process migrates its own scratch database, so they share no rows;
the test count and both coverage gates are the same as a serial run. `make test-api` stays serial:
on a WSL checkout under `/mnt/` the suite is bound by the file system, and 4 processes took as long
(17 minutes). The suggestions timing test asserts its 150 ms budget only where `CI` is unset; in CI
it checks that the query plan uses `ix_prescription_items_clinic_id_medicine_name` (developer
decision, 11 Nov 2026, after a 569 ms run on a loaded runner).

Not cached, deliberately: Docker image layers. The API image runs `apt-get upgrade`, and a cached
layer would keep old packages until the cache was evicted, so Trivy would scan an image that a
fresh build no longer produces.

## 6. Phase verification template

Every phase hand-off includes:

```markdown
### How to verify M<x>-P<y>
1. `make up && make migrate`
2. `<command or click path>` → expected: `<exact output>`
3. Failure path: `<command>` → expected: `<error code and status>`
4. `make lint typecheck test` → all green
```
