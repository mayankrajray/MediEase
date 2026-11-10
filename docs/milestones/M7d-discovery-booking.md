# M7d — Patient discovery, clinic and doctor profiles, booking redesign

**Status:** parked. Recorded 10 Nov 2026; work starts after M7c-P7 (modules M7–M10) is finished.
Branch and issue are opened when the milestone starts (one branch, one PR, ADR-0011).

**Reference:** [`M7d-reference-image.png`](M7d-reference-image.png), from the developer: a
"Doctor Profile" screen (photo, name, specialty, rating, stat row, About with Read More, a date
strip with a calendar control, time chips, "Book An Appointment") and a "Confirm and Pay" screen
(appointment summary, payment details with consultation, admin fee and total, payment method,
"Pay Now"). It sets the **layout and flow**, not the colours or the data: MediEase keeps its own
design system (`DESIGN.md`, brand `#147D72`, not the reference's green), and every value shown must
come from real data (see "Data gaps").

This file is also the parking place for every further change the developer asks for while
M7c-P7 runs. Add them under "Backlog added during M7c-P7".

## 1. The brief (developer, 10 Nov 2026)

1. **Search inputs.** The icons in "Search Doctors" and "Search City" sit too low. Centre them
   properly against the input, without arbitrary transforms or magic offsets.
2. **Search results.** Clean doctor and clinic cards; no schedules on the results.
3. **Clinic profile.** A dedicated route with a hero (name, address, contact, directions), a
   "Find a doctor" search inside the clinic, filters (qualification such as MBBS/MD/MS,
   specialization, medical requirement, fee, availability) and doctor cards with "View profile".
4. **Doctor profile.** A dedicated page: identity, stats only where real data exists, "About"
   with Read More, a link back to the clinic.
5. **Date selection.** Only the next 3–4 bookable dates, horizontally scrollable, plus a calendar
   control for later dates. Past dates never offered.
6. **Time selection.** Times appear only after a date is selected. Badges such as
   "40 slots remaining" or "Fully booked" from real data. A full time can never be booked;
   guard against stale availability.
7. **Confirmation.** A summary of doctor, clinic, date, time, fee, charges and total. No new
   payment provider.
8. **Responsive.** Checked at 320, 375, 390, 430, 768, 1024 and 1440 px; no horizontal scroll.
9. **Rules.** No hardcoded data, no fake ratings or counts, no schema or contract change unless
   needed, no Redis.
10. **Deliverables.** Findings, plan, changed files, before and after screenshots, test results,
    API gaps.

## 2. Findings (audit, 10 Nov 2026)

- **Icon offset.** `features/discovery/FindPage.tsx` places the icons at `absolute top-[1.6rem]`
  inside a wrapper that also holds the field label, so the offset depends on the label height.
  Fix: a wrapper around the input only, icon centred with `inset-y-0 flex items-center`.
- **Routes today.** `/find` (server page). `/c/[slug]` and `/c/[slug]/doctors/[doctor]` both
  render `features/public-clinic/PublicClinicPage.tsx` (402 lines, `profileOf` prop,
  `requestHref()`, `DayOffers`). The request form is `/portal/request` →
  `features/portal/RequestBooking.tsx` (sign-in required).
- **Public clinic API** `GET /api/v1/public/clinics/{slug}`: name, slug, address, phone,
  timezone, booking mode, map URL, specialties, and doctors with id, display name,
  qualification, specialty, weekly hours, languages, fee.
- **Availability API** `GET /api/v1/public/clinics/{slug}/availability?doctor_id&from&via`:
  14 days of sessions with `places_left` and slot times; only times at least 2 h ahead and not
  held; **days with no place are omitted**.
- **Search API** filters: `q, city, pincode, specialty, language, available`. Doctor hits carry
  `next_available` and the clinic; clinic hits carry their doctors.
- **Booking flow today.** Request → the clinic confirms. Status ends at "Requested".
- **Page weights** (budget 200 KB, NFR-02): `/c/sample-clinic` 184.6 KB, `/find` 163.9 KB.

## 3. Data gaps (show nothing rather than invent)

| Reference shows | MediEase has | Plan |
|---|---|---|
| Doctor photo | none | initials avatar |
| Rating, reviews | none; out of scope in `docs/specs/discovery.md` | hidden |
| Patients count, years of experience | none | hidden; stats row shows only real facts (fee, languages, qualification, next free day) |
| About / biography | none | built from qualification, specialty, languages and hours; Read More only when long |
| Clinic logo, cover, about, facilities | none | text hero |
| "Fully booked" | days with no place are omitted by the API | show "No free times" for the gap; a true "Fully booked" badge needs an API change (API gap) |
| Admin fee, online payment | none; pay at the clinic | "Pay at the clinic", no other charges, total = fee |
| Clinic-page availability filter | per-doctor availability call | fetched only when the filter is turned on |

## 4. Decisions to confirm when M7d starts

1. Keep request-then-clinic-confirms, ending at "Requested" (instant booking needs an API and
   product-rule change).
2. Fee shown as "Pay at the clinic", no other charges (no payment provider exists).
3. "Medical requirement" filter = text match on specialty and qualification, with specialty
   suggestion chips and a "this is not medical advice" note (a symptom→specialty map needs
   clinical review; AGENTS.md §7 forbids medical advice).
4. No date pre-selected, so no times show until a date is chosen.

## 5. Plan (front end only)

1. Search icon alignment in `FindPage.tsx`; clean result cards.
2. Clinic profile: `PublicClinicPage.tsx` keeps the clinic only; new `ClinicDoctors.tsx` (search,
   filters, doctor cards) and `doctorFilters.ts` (pure, unit-tested).
3. Doctor profile: new `DoctorProfile.tsx` on `/c/[slug]/doctors/[doctor]` (URL kept).
4. `AppointmentPicker.tsx` + `availability.ts`: next 4 bookable dates, a calendar limited to the
   14-day window, times after a date is chosen grouped into morning, afternoon and evening,
   "N slots remaining" badges (warning at 3 or fewer), refetch when data is older than 60 s and
   before moving to the confirmation.
5. `RequestBooking.tsx` becomes the confirmation summary with "Pay at the clinic"; the server
   still rejects a full or held time (existing rule), and the page shows that message.
6. Wording in `lib/i18n/booking-request.ts` and `lib/i18n/find.ts` (English and Hindi).
7. Tests: update the unit tests of the touched components, add tests for `doctorFilters.ts` and
   `availability.ts`, update `e2e/discovery.spec.ts`, `booking-requests.spec.ts`,
   `booking-answers.spec.ts` and `booking-support.ts` (`requestPath`, `askFor`), and run them.
8. Screenshots at the seven widths, the overflow audit and the page-weight check; update
   `docs/specs/discovery.md` and the booking-requests spec.

Estimate: about 5–6 hours.

## 6. API gaps (need a backend milestone, not M7d)

- A "Fully booked" day state in the availability response.
- Doctor photo and biography fields (with consent and moderation rules).
- Clinic logo, cover and facilities.
- Ratings and reviews (currently out of scope).
- Instant booking and online payment, if ever wanted.

## Backlog added during M7c-P7

_(Changes the developer asks for while M7–M10 are being redesigned, and any backend change those
modules turn out to need, are recorded here.)_
