# e2e

Playwright journeys from `docs/TESTING.md` §3, run against the real stack with seeded synthetic
data: `make up && make seed && make install-web && make e2e`. `make e2e` runs them in the
official Playwright image (its tag must equal `@playwright/test` in `package.json`) on the compose
network, at `http://web:3000`. Config: `playwright.config.ts` (Chromium, 1366×768, no retries,
traces kept on failure). This folder is not in the web image (`.dockerignore`).

| Spec | Journey | From |
|---|---|---|
| `patients-duplicate-phone.spec.ts` | Register on a family's phone → use the existing patient → register a new family member → find them | M2-P5 |
| `booking-three-interactions.spec.ts` | Book → the patient → Confirm from the queue, at most 3 interactions (AC6) | M3-P5 |
| `queue-two-browsers.spec.ts` | Desk marks a patient arrived; the doctor's board shows it within one poll (AC4) | M3-P5 |
| `live-queue-etag.spec.ts` | A repeat queue request with its ETag is a 304 through the web origin (R12) | M3-P4 |
