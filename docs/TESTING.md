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
| Register patient with existing phone → choose existing | M2 |
| Book slot → mark arrived → start consultation → issue Rx → print PDF | M4 |
| Open patient link on a 360-px viewport → wrong last-4 → correct last-4 → view Rx | M4 |
| Issue Rx with follow-up → reminder scheduled → worker sends via console adapter → status updates | M5 |
| Patient replies STOP → opted out → next reminder skipped | M5 |

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
7. Coverage ≥ 80% on `domain/` and `application/` (NFR-14)

End-to-end tests run on every PR once the stack exists (M3+), and nightly against staging (M6+).

## 6. Phase verification template

Every phase hand-off includes:

```markdown
### How to verify M<x>-P<y>
1. `make up && make migrate`
2. `<command or click path>` → expected: `<exact output>`
3. Failure path: `<command>` → expected: `<error code and status>`
4. `make lint typecheck test` → all green
```
