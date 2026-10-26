# Spec: Directory search and booking from discovery

| Field | Value |
|---|---|
| Requirements | FR-DIS-01, 02, 04, 05 (P6); FR-DIS-08 (P7); NFR-17, NFR-19 |
| Milestone / phases | M6c / P6–P7 (profiles and the discoverability rule: `clinic-onboarding.md` R50–R64) |
| Status | P6 (R1–R10, AC1–AC4) and P7 (R11–R15, AC5–AC6) approved in advance by the developer 26 Oct 2026 and built |
| Owner | Developer |
| Last updated | 2026-10-26 |

## 1. Context
Before M6c a patient could book only at a clinic whose link they already had. Discovery lets a
patient find a verified, listed clinic or doctor by name, specialty, language, place and
availability, and ask for a time from the result (PRD v1.2 C7, C8). Decisions: ADR-0021.

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Anyone, signed out | Search clinics and doctors; open profiles | See an undiscoverable clinic in results; see anything a clinic does not publish |
| A signed-in patient | Ask for a time from a profile (the M6b request flow) | Ask a clinic that has left the directory from a stale result |

## 3. Domain model
No new entity. Search reads the published columns of `clinics` and `doctors` and applies
`is_discoverable` (clinic-onboarding R55) and `Doctor.is_public` (R59) to every candidate.

## 4. Behaviour

### Search (P6)
- **R1** `GET /api/v1/public/search/clinics` and `.../doctors` take `q` (up to 100 characters,
  lower-cased, spaces collapsed), `city` (up to 100), `pincode` (six digits, not starting with 0),
  `specialty` (up to 100, compared case-insensitively with the clinic's specialties and the
  doctor's specialty), `language` (one of `options.languages`) and `available` (`true`/`false`).
  A bad value is 422 `REQ_VALIDATION_FAILED` naming the field; the value is never echoed.
- **R2** At most 40 candidates are checked and at most 20 returned. Only clinics that pass the
  discoverability rule appear, with only their public doctors; doctor results are public doctors
  of such clinics.
- **R3** Place: same PIN (0), same city (1), same PIN district — the first three digits (2),
  elsewhere (3). With a `pincode` or `city`, only ranks 0–2 are returned.
- **R4** `next_available` is the first clinic-local day, within 7 days from today, with a free
  time (the public page's offers, without writing). `available=true` keeps only results that
  have one.
- **R5** Order: relevance (trigram `word_similarity` of `q` with the clinic's or doctor's name; a
  specialty containing `q` counts 0.9) in steps of 0.1, then place, then the earliest free day,
  then the name. Without `q` every candidate scores 0. With `q`, a score under 0.3 is not a match.
- **R6** A suspended, unlisted, unverified or problem-holding clinic and a hidden, inactive or
  unverified doctor are never returned (the rule is applied on every request: no index to lag).
- **R7** The bodies are allow-lists: a clinic hit carries its slug, name, address, city, state,
  PIN, specialties, its public doctors (ID, name, specialty) and `next_available`; a doctor hit
  its ID, name, qualification, specialty, languages, fee, `next_available` and the clinic's slug,
  name, city, state and PIN. `options` lists the specialties and languages for the form.
- **R8** No session; the public read limit applies (`PRT_RATE_LIMITED`, 429). `no-store`,
  `noindex`. Logs say how many results and whether words or a place were given, never the words.
- **R9** `/find` renders the search on the server from a plain GET form (it works without
  JavaScript), English or Hindi (`?lang=hi`, or the portal language cookie), 360 px first; tabs
  for doctors and clinics; a result opens the clinic page or the doctor profile. `/find` without a
  query is indexable; a results page is `noindex, follow`.
- **R10** Every result says the first free day in words or "No free time in the next 7 days".

### Discovery to booking (P7)
- **R11** Result links carry `via=directory`. The public clinic body asked with
  `via=directory` (and the availability asked with it) is the same 404 as an unknown slug when the
  clinic is not discoverable, and a doctor who is not public is absent: a stale result never
  leads to a clinic that has left the directory (FR-DIS-08, NFR-19). Without `via` the page
  follows `has_public_page` (a clinic's own link keeps working, FR-DIS-07).
- **R12** From a profile the patient picks a time; the M6b request form asks them to sign in or
  sign up and returns to the same time (booking-requests R10); the request lands in that clinic's
  inbox like any other.
- **R13** The time links of a page opened `via=directory` keep `via=directory`, and the request
  form checks the clinic is still discoverable before sending (the same 404 answer otherwise).
- **R14** The portal's *Find a doctor* opens `/find` (it was an interim page until M6c).
- **R15** No ranking is paid for, and no result is promoted (PRD §8.14).

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/public/search/clinics` | R1 query | 200 `{items: ClinicSearchHit[], options}` | 422, 429 |
| GET | `/api/v1/public/search/doctors` | R1 query | 200 `{items: DoctorSearchHit[], options}` | 422, 429 |
| GET | `/api/v1/public/clinics/{slug}?via=directory` | R11 | 200 `PublicClinic` | 404 |
| GET | `/api/v1/public/clinics/{slug}/availability?doctor_id=&via=directory` | R11 | 200 | 404 |

## 6. UI notes
`/find`: a heading, the emergency notice, the form (what, where, specialty, language, *Free in
the next 7 days*, *Search*), the two tabs, then results as cards. Loading is the server render;
errors are one plain sentence (`role="alert"`): unavailable, too many searches, a bad PIN.

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| A search | none (log `search.clinics` / `search.doctors` with counts) | — | none |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| A clinic suspended between the search and the click | The page opened `via=directory` is 404 |
| A clinic that unlists itself | Gone from search at once; its own link (no `via`) still works |
| A doctor's registration edited | The clinic stays listed but stops being discoverable until re-verified (clinic-onboarding R46, R55) |
| `where` is "560001" | Treated as a PIN; "Pune" as a city |
| No query at all | Up to 20 discoverable results, those with the soonest free time first |

## 9. Acceptance criteria
- **AC1 (FR-DIS-01)** — Given a discoverable clinic A and an unlisted clinic B, when anyone
  searches clinics, then only A is returned, by its name, its doctor's name or its specialty.
- **AC2 (FR-DIS-02, 04)** — Given A's doctor speaks Hindi, then a doctor search for Hindi finds
  them and one for Tamil does not; a search near A's PIN or PIN district finds A, one in another
  district does not.
- **AC3 (FR-DIS-05)** — Given A's doctor has a free time this week, then `available=true` keeps
  them; without weekly hours A is not discoverable and not found.
- **AC4 (R6)** — Given a hidden doctor or a suspended clinic, then neither appears.
- **AC5 (FR-DIS-08)** — Given a result for A and then A unlisted, when the profile is opened
  `via=directory`, then it is 404; opened from A's own link it still shows.
- **AC6 (R12)** — Given a signed-out visitor on `/find`, when they open a doctor's profile and
  pick a time, sign up and verify, then the request lands in A's inbox (Playwright).

## 10. Observability
Log events `search.clinics` and `search.doctors` (results, words given, place given);
`public.page_not_found` (slug digest only) for R11. Error codes: `REQ_VALIDATION_FAILED`,
`PRT_RATE_LIMITED`, `REQ_NOT_FOUND`.

## 11. Out of scope
Maps and distances (no coordinates, ADR-0021); ratings and reviews; paid placement; a read model
(ADR-0021 "when to revisit").

## 12. Open questions
None.
