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
| `patient-link-360.spec.ts` | The issued sample opens at 360 px after the last-4 check, in English and Hindi; five wrong answers lock the link (AC2, AC3) | M4-P5 |
| `consultation-keyboard.spec.ts` | The doctor starts from the queue, types the sample with the keyboard, previews, issues, prints; front desk prints from the row; a second tab's save stops the first (NFR-09, D6) | M4-P6 |
| `reminders-follow-ups.spec.ts` | An issued follow-up's reminder on the consultation and the profile, with the message history; Book follow-up from the pending list (on `make seed`'s overdue follow-up); ops open the month's messaging costs (R16-R18) | M5-P6 |

Printing opens a tab on a `blob:` URL. Headless Chromium has no PDF viewer, so there the PDF
arrives as a download of that URL; the journey checks the download starts with `%PDF-`.
