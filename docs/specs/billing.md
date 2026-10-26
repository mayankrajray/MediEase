# Spec: Billing and documents

| Field | Value |
|---|---|
| Requirements | FR-BIL-01 (P1); FR-BIL-02..07, FR-VIS-04, FR-SUB-01 in later phases |
| Milestone / phases | M6d / P1–P7 (design: `docs/milestones/M6d-billing-and-documents.md`) |
| Status | P1 (R1–R12, AC1–AC3) approved 26 Oct 2026 and built; P2–P7 to be specified per phase |
| Owner | Developer |
| Last updated | 2026-10-26 |

## 1. Context
Clinics bill at the desk on paper or in a separate tool, so the visit and the money never meet
(PRD FR-BIL). M6d brings bills, payments, receipts and the daily collection into MediEase. P1 is
the fee schedule every bill draws from: the services a clinic charges for and their prices. It
also becomes the one source of the public profile fee (D8). Money is integer paise (B1).

## 2. Actors and permissions
| Actor | Can | Cannot |
|---|---|---|
| Owner (`FEES_MANAGE`, `BILLING_MANAGE`) | Read the schedule; add, rename, reprice, reorder, retire and restore services; set or remove a doctor's own price; choose whether a doctor's fee is shown publicly (`CLINIC_MANAGE`, on *Directory*) | Delete a service |
| Doctor, front desk (`BILLING_MANAGE`) | Read the schedule (to draft bills, from P2) | Change any price or service (403) |
| Another clinic | Nothing (404; the schedule it reads is its own) | — |

## 3. Domain model
- **ClinicService** (`clinic_services`, tenant): name (1–80 characters), kind (`CONSULTATION`,
  `FOLLOW_UP`, `PROCEDURE`, `OTHER`), optional default price in paise, active, position (1–100).
- **DoctorPrice** (`doctor_service_prices`, tenant): a doctor's own price for one service, unique
  per service and doctor.
- **Doctor.show_fee**: whether the public profile shows the doctor's consultation price.

## 4. Behaviour
- **R1** A clinic has at most 100 services (`BIL_TOO_MANY_SERVICES`, 409). A new service goes
  last unless a position is given.
- **R2** Every clinic starts with *Consultation* (position 1) and *Follow-up* (position 2),
  active and without a price: at clinic creation, in the seed, and for existing clinics in
  migration 0036.
- **R3** Active names are unique per clinic, ignoring case (`BIL_SERVICE_NAME_TAKEN`, 409, field
  `name`). Changes to one clinic's schedule take the clinic row lock, and a partial unique index
  decides between two writers.
- **R4** A doctor's price for a service is their own price, else the service's default, else none.
  Setting `price_paise: null` removes the doctor's own price.
- **R5** `PATCH` changes only the fields sent; `default_price_paise: null` removes the default; an
  empty body is 422. `active: false` retires a service and `true` restores it (the name rule
  applies again). A service is never deleted. A change applies from now on: bills already issued
  keep their lines (B3, from P2).
- **R6** A price is 0 to 10 000 000 paise (₹1,00,000, B1), checked in the request model, the
  domain and a database CHECK; outside it is 422 `REQ_VALIDATION_FAILED` naming the field.
- **R7** `GET` needs `BILLING_MANAGE`; every change needs `FEES_MANAGE`. Another clinic's service
  or doctor is 404.
- **R8** Every answer is the whole schedule: every service (active and retired) in position order,
  each with one entry per active doctor (`own_price_paise`, effective `price_paise`), and the
  active doctors. `Cache-Control: no-store`.
- **R9** Every change is audited (`fees.service_added`, `fees.service_changed`,
  `fees.doctor_price_set`, category *Billing*) with the service ID, kind, amounts in paise and the
  active flag, or the doctor ID and price; never a name.
- **R10** (D8) A doctor's public fee is their price for the clinic's first active `CONSULTATION`
  service in position order. The public clinic page, the doctor profile and doctor search show it
  only when `show_fee` is on; otherwise `fee_paise` is null.
- **R11** Migration 0036 copies each doctor's M6c public fee (`doctors.fee_paise`) into their own
  *Consultation* price and turns `show_fee` on where there was one, so public profiles keep the
  same fee. `doctors.fee_paise` stays (expand-only), deprecated: never written or read.
- **R12** The doctor profile `PUT` (*Directory*) takes `languages` and `show_fee`, each optional
  (left out keeps the doctor's); `fee_paise` is refused (422). The listing answers each doctor's
  effective consultation price (`fee_paise`) and `show_fee`.

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/clinic/fees` | — | 200 `FeeSchedule` | 401, 403 |
| POST | `/api/v1/clinic/fees/services` | `NewService` | 201 `FeeSchedule` | 403, 409 `BIL_SERVICE_NAME_TAKEN` / `BIL_TOO_MANY_SERVICES`, 422 |
| PATCH | `/api/v1/clinic/fees/services/{service_id}` | `ServiceChange` | 200 `FeeSchedule` | 403, 404, 409, 422 |
| PUT | `/api/v1/clinic/fees/services/{service_id}/doctors/{doctor_id}` | `{price_paise}` | 200 `FeeSchedule` | 403, 404, 422 |
| PUT | `/api/v1/clinic/listing/doctors/{doctor_id}/profile` | `{languages?, show_fee?}` | 200 `ClinicListing` | 403, 404, 422 |

Contract 0.43.0.

## 6. UI notes
*Settings → Fees* (`/settings/fees`, in the owner's menu): a table of prices by service and
doctor (marking a doctor's own price) that every billing role can read; for owners, one card per
active service (name, kind, default price, each doctor's own price, *Retire*), *Add a service*,
and the retired services with *Restore*. Amounts are typed in rupees (up to two decimals, commas
allowed) and sent as paise; a bad amount is refused in the form before sending. *Directory*
replaces the fee box with *Show the consultation fee publicly*, saying the price and linking to
*Fees*.

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| Service added | `fees.service_added` | — | — |
| Service changed, retired or restored | `fees.service_changed` | — | — |
| Doctor price set or removed | `fees.doctor_price_set` | — | — |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| A retired service's name is reused | Allowed; restoring the old one then fails with `BIL_SERVICE_NAME_TAKEN` |
| No active consultation service | Every doctor's public fee is null |
| An inactive doctor | Not in the schedule's doctors; their stored prices stay |
| Two owners add the same name at once | One wins; the other gets `BIL_SERVICE_NAME_TAKEN` |

## 9. Acceptance criteria
- **AC1 (FR-BIL-01, R2)** — Given a clinic created through onboarding, when the owner opens
  *Fees*, then *Consultation* and *Follow-up* are there without prices.
- **AC2 (FR-BIL-01, R3–R6, R9)** — Given the owner, when they price services and set a doctor's own
  price, then the effective prices follow R4, a duplicate active name is 409, a price over
  ₹1,00,000 is 422, and every change is in the audit log.
- **AC3 (R7)** — Given a doctor or the front desk, when they read *Fees*, then they see the
  prices, and any change is 403; another clinic's schedule is never visible.

## 10. Observability
Log `fees.service_added` with the clinic ID and kind. Error codes: `BIL_SERVICE_NAME_TAKEN`,
`BIL_TOO_MANY_SERVICES` (docs/ERRORS.md).

## 11. Out of scope
Tax (D3: no GST fields), price history, packages and per-patient discounts (bills, P2).

## 12. Open questions
None for P1.
