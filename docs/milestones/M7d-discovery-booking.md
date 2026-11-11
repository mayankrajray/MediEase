# M7d — Patient discovery, clinic and doctor profiles, booking redesign

**Status:** active from 11 Nov 2026 (issue #71, branch `m7d/71-discovery-booking`, PR #72). The
approved phases and UX rules are in §7.

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
| Doctors available on a date | per-doctor availability call | one call per doctor for the 14 days, cached; the date strip reads from it |

## 4. Decisions (developer, 11 Nov 2026)

1. **Keep request-then-clinic-confirms**, ending at "Requested". No instant booking.
2. **Fee shown as "Pay at the clinic"**, no other charges; total = fee.
3. **No filters at all on the clinic page.** No "medical requirement" filter, no qualification,
   specialty, fee or availability filters: small clinics do not need them. The clinic page shows
   the doctors who are available on the chosen date at that clinic.
4. **Today is selected when booking starts.** The date strip lists the next 3–4 dates (today
   first) and a calendar picker for later dates (within the 14-day window, never past dates).
   Only the chosen date's data is shown. For that date, times are grouped into **Morning,
   Afternoon and Evening**, each showing at most three slots at first, with the rest of that
   part of the day revealed on request ("Show all morning times").

(This replaces the four proposals the audit made on 10 Nov: proposal 3's text-match filter is
dropped, and proposal 4's "no date pre-selected" becomes "today pre-selected".)

## 5. Plan (front end only)

1. Search icon alignment in `FindPage.tsx`; clean result cards.
2. Clinic profile: `PublicClinicPage.tsx` keeps the clinic only; new `ClinicDoctors.tsx`: the
   date strip and the doctors available on the chosen date, as cards (no filters, decision 3).
3. Doctor profile: new `DoctorProfile.tsx` on `/c/[slug]/doctors/[doctor]` (URL kept).
4. `AppointmentPicker.tsx` + `availability.ts`: today selected, the next 3–4 dates and a
   calendar limited to the 14-day window; the chosen date's times grouped into morning, afternoon
   and evening, three each until "Show all"; "N slots remaining" badges (warning at 3 or fewer);
   refetch when data is older than 60 s and before moving to the confirmation.
5. `RequestBooking.tsx` becomes the confirmation summary with "Pay at the clinic"; the server
   still rejects a full or held time (existing rule), and the page shows that message.
6. Wording in `lib/i18n/booking-request.ts` and `lib/i18n/find.ts` (English and Hindi).
7. Tests: update the unit tests of the touched components, add tests for `availability.ts`, update `e2e/discovery.spec.ts`, `booking-requests.spec.ts`,
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

| # | Item | Why it waits | Found in |
|---|---|---|---|
| B1 | **Prescription PDF layout 4 with the MediEase emblem** (approved 9 Nov 2026, plan §9 Q3): replace the placeholder mark `apps/api/.../pdf/assets/mediease-mark.svg` with the outlined emblem, as a new layout version so issued prescriptions keep their look (spec R13–R14) | It is an API change (PDF renderer, assets, layout version, tests); the developer asked for no backend change in M7c-P7 (10 Nov 2026) | M8 |
| B2 | **Portal page weight headroom**: portal pages are at 185–194 KB of the 200 KB budget (NFR-02), most of it the shared framework chunks (about 140 KB). Any new portal feature should be measured; options are a lighter data layer for the portal or splitting the bell's polling out of the first load | Needs a measured design, not a restyle | M7 |

## 7. Approved phases and UX rules (developer, 11 Nov 2026)

Priority: fast booking with few decisions, clear availability, no surprises.

| Phase | Scope |
|---|---|
| P1 | Search: icons centred on the input itself; result cards with one "Next available: Tue, 12 Nov" line; no weekly hours or timetables; no "Free from" |
| P2 | `features/booking/availability.ts` (pure) and `AppointmentPicker.tsx`: today selected; the next 4 dates; the browser's date picker limited to today through day 14; times of the chosen date grouped into morning (before 12:00), afternoon (12:00–17:00) and evening (from 17:00), three each until "Show all"; places-left badges (warning at 3 or fewer); data refreshed when older than 60 s and before confirmation |
| P3 | Doctor profile (`/c/[slug]/doctors/[doctor]`): back link, initials avatar, real facts only, About with Read more, the picker, "Request this time", a link to the clinic |
| P4 | Clinic page: text hero (address, call, directions, share), the date strip, the doctors free on that date with "View profile"; no filters |
| P5 | Confirmation in `RequestBooking.tsx`: doctor, clinic, date and time; consultation fee, "Pay at the clinic", total = fee; the request form; "Requested" only after the server's answer |
| P6 | Journeys and full `make e2e`; screenshots at 320, 375, 390, 430, 768, 1024, 1440 px; page weights; specs and this record |

**Defaults, as refined:**

1. **Calendar:** the native date input, `min` today and `max` day 14. A date with no times says
   "No available times on this date" and offers a "Next available" action that selects it.
2. **Token sessions:** grouped under morning, afternoon and evening like slots, one compact row
   each (`09:00–13:00 · 12 places left`) with a "Choose" button. Counts come from the latest
   answer and are refetched after a selection and before confirmation.
3. **Search cards:** one line, "Next available: Tue, 12 Nov", or "No available times in the
   next 14 days".
4. **Request this time:** sticky at the bottom on phones, above the safe-area inset, with space
   reserved so it never covers content; inline from `sm` up; disabled until a valid time is chosen.

**Rules for every screen in M7d:**

- Selected, unavailable, loading and error states look different, and not by colour alone
  (`aria-pressed`, text, icon).
- Selections survive going back and recovering from an error: the chosen date and time live in
  the address (`?date=&session=&slot=`), so Back and reload return to them.
- Nothing says "booked" or "confirmed" before the server answers; the end state is "Requested",
  and the clinic confirms.
- One submission at a time (the button shows it is sending); success and failure are said
  plainly, and a taken time links back to the doctor's times.
- Touch targets at least 44 px; visible keyboard focus; the existing tokens (`DESIGN.md`) and the
  accessibility checks of the journeys (axe, no sideways scroll).
