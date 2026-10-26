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
| `clinic-application.spec.ts` | A solo doctor applies at 360 px (a text file renamed `.pdf` is refused), confirms from Mailpit; ops sees it waiting, takes it, verifies the doctor and approves; the owner's invitation arrives by email and the clinic has no public page yet (clinic-onboarding AC1, AC2, AC4, AC9-AC11). Uses one of the 5 applications a day per address | M6c-P1..P3 |
| `discovery.spec.ts` | At 360 px: the landing page (indexable, under 200 KB, axe, LCP logged), *Find a doctor*, a search for the seeded doctor, the profile from the result (`via=directory`), a time, the fake Google sign-in back to the form, *Requested*; an empty place and an unknown profile (discovery AC1, AC5, AC6) | M6c-P5..P8 |

Printing opens a tab on a `blob:` URL. Headless Chromium has no PDF viewer, so there the PDF
arrives as a download of that URL; the journey checks the download starts with `%PDF-`.
