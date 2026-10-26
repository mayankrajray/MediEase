# Spec: Billing and documents

| Field | Value |
|---|---|
| Requirements | FR-BIL-01 (P1); FR-BIL-02..07, FR-VIS-04, FR-SUB-01 in later phases |
| Milestone / phases | M6d / P1–P7 (design: `docs/milestones/M6d-billing-and-documents.md`) |
| Status | P1 (R1–R12, AC1–AC3), P2 (R13–R30, AC4–AC8) and P3 (R31–R42, AC9–AC12) approved 26 Oct 2026 (P2–P7 in advance) and built; P4, P5 to follow |
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

### Bills and credit notes (P2; ADR-0022)
- **R13** A bill belongs to one patient of the clinic and, optionally, to one of their **completed**
  visits (`BIL_VISIT_NOT_COMPLETED`, 409; another patient's visit is 422). A visit's bill is for
  the visit's doctor. A bill without a visit names a doctor or none. Nothing clinical is copied
  from the visit (B3).
- **R14** A visit has at most one open bill, a draft or an issued one (`BIL_VISIT_BILLED`, 409,
  with `details.bill_id`; a partial unique index). A cancelled bill frees the visit.
- **R15** Drafted from a visit without lines, a bill starts with the clinic's first active
  consultation service at the doctor's price (R4, R10), if it has one.
- **R16** A line names a service of the fee schedule or is typed. A missing description is the
  service's name, and a missing price is the bill doctor's price for it (no price: 422). A line is
  `unit price × quantity` (1–99) less its own discount. The bill discount is shared across the
  lines in proportion to their value by largest remainder, so the shares add up exactly. Each
  line's `amount_paise` is what it finally costs, and the total is their sum.
- **R17** Discounts are none, an amount in paise (at most what it applies to), or a percent in
  hundredths (at most 100%, rounded half up to the paisa). A unit price is at most ₹1,00,000
  (B1), a bill at most ₹10,00,000, 50 lines. Out of range is 422 naming the field.
- **R18** A draft is replaced as a whole: lines, discount and notes (up to 500 characters, printed
  on the bill, never clinical). A visit's bill and a doctor's own bill keep their doctor (422).
- **R19** A draft can be discarded (deleted). An issued bill cannot (`BIL_NOT_DRAFT`, 409).
- **R20** *Issue* gives the next number of the clinic's financial year (D1, B5) and freezes the
  bill. An empty draft cannot be issued (`BIL_EMPTY`, 409), and nothing else can change it after
  issue (`BIL_NOT_DRAFT`). The bill date is the clinic-local day of issue.
- **R21** Every role holds `BILLING_MANAGE`, but a doctor reaches only bills with their own doctor
  profile: another doctor's bill is 404. A doctor cannot draft for another doctor or list another
  doctor's bills (`BIL_NOT_YOURS`, 403). Owners and the front desk reach every bill.
- **R22** The list is newest first, 50 at a time (`next_cursor`), filtered by patient, doctor and
  state. It holds bills only; credit notes are shown on their bill.
- **R23** A credit note reverses chosen lines of an **issued** bill (`BIL_NOT_ISSUED`, 409), or
  every open line when none are named, at their final amounts. It needs a reason (up to 200
  characters).
- **R24** A line is credited at most once (`BIL_LINE_ALREADY_CREDITED`, 409; a unique index).
- **R25** A credit note is numbered in its own series, `<prefix>/CN/26-27/0001`, and is always
  issued. The bill records `credited_paise`.
- **R26** When every line is credited the bill is `CANCELLED`. Crediting every line gives back
  exactly the total.
- **R27** Issuing and crediting take the clinic row lock, then the bill row. Editing takes the
  bill row only. Two issues at once get two consecutive numbers.
- **R28** The balance is `total − credited − paid + refunded`. It is null for a draft, and
  negative when the clinic owes the patient (refunds, P3).
- **R29** Every change is audited (`bill.drafted`, `bill.changed`, `bill.discarded`,
  `bill.issued`, `bill.credited`; category *Billing*) with IDs, numbers, counts and amounts only.
- **R30** A bill's body names the patient (ID, code, name) and the doctor; it never carries a
  diagnosis, a note from the visit or a medicine.

### Payments, refunds and dues (P3; B6, D2)
- **R31** A payment or refund belongs to one bill. A payment needs an `ISSUED` bill. A refund needs
  an issued or cancelled bill. A draft takes neither (`BIL_NOT_ISSUED`, 409).
- **R32** A payment never exceeds the balance, and a refund never exceeds what is owed back
  (`BIL_PAYMENT_TOO_LARGE`, 409, with `details.most_paise`). Partial payments are fine. There is
  no advance or deposit.
- **R33** A refund is possible only when a credit note leaves the bill overpaid (balance below 0).
- **R34** Recording takes the bill row lock, so two payments at once can never both fit a balance
  meant for one.
- **R35** A payment or refund is voided on the clinic-local day it was recorded only
  (`BIL_VOID_TOO_LATE`), once (`BIL_ALREADY_VOIDED`), with a reason up to 200 characters. Its
  amount goes back on the bill. Later corrections are a credit note and a refund.
- **R36** A payment is not voided while a refund taken out of it stands (`BIL_VOID_REFUNDED`): void
  the refund first, so refunded never exceeds paid.
- **R37** A payment records its mode (`CASH`, `UPI`, `CARD`), amount in paise (1 to ₹10,00,000), an
  optional UPI or card reference (up to 40), who took it, when, and the clinic-local day (the
  collection's day, P5).
- **R38** Payments are never edited or deleted. A void keeps the row with its time, author and
  reason.
- **R39** *Dues* (`COLLECTION_VIEW`, owners and the front desk) lists patients with a positive
  balance on issued bills, the largest first, with the number of bills, the amount and the oldest
  bill date, and the total. 200 patients at most.
- **R40** The queue shows what each patient owes (`dues_paise`, an amount only), and so does the
  patient profile for those with `COLLECTION_VIEW`.
- **R41** Every payment and void is audited (`payment.recorded`, `payment.voided`) with the bill
  ID, kind, mode and amount.
- **R42** A doctor records payments on their own bills only (D2, R21); another doctor's bill is 404.

## 5. API surface
| Method | Path | Request | Success | Errors |
|---|---|---|---|---|
| GET | `/api/v1/clinic/fees` | — | 200 `FeeSchedule` | 401, 403 |
| POST | `/api/v1/clinic/fees/services` | `NewService` | 201 `FeeSchedule` | 403, 409 `BIL_SERVICE_NAME_TAKEN` / `BIL_TOO_MANY_SERVICES`, 422 |
| PATCH | `/api/v1/clinic/fees/services/{service_id}` | `ServiceChange` | 200 `FeeSchedule` | 403, 404, 409, 422 |
| PUT | `/api/v1/clinic/fees/services/{service_id}/doctors/{doctor_id}` | `{price_paise}` | 200 `FeeSchedule` | 403, 404, 422 |
| PUT | `/api/v1/clinic/listing/doctors/{doctor_id}/profile` | `{languages?, show_fee?}` | 200 `ClinicListing` | 403, 404, 422 |

| GET | `/api/v1/clinic/bills?patient_id&doctor_id&status&cursor` | — | 200 `BillPage` | 403 `BIL_NOT_YOURS`, 422 |
| POST | `/api/v1/clinic/bills` | `NewBill` | 201 `Bill` | 403, 404, 409 `BIL_VISIT_BILLED` / `BIL_VISIT_NOT_COMPLETED`, 422 |
| GET, PUT, DELETE | `/api/v1/clinic/bills/{bill_id}` | —, `BillChange`, — | 200 `Bill`, 204 | 404, 409 `BIL_NOT_DRAFT`, 422 |
| POST | `/api/v1/clinic/bills/{bill_id}/issue` | — | 200 `Bill` | 404, 409 `BIL_NOT_DRAFT` / `BIL_EMPTY` |
| POST | `/api/v1/clinic/bills/{bill_id}/credit-notes` | `CreditNoteInput` | 201 `Bill` | 404, 409 `BIL_NOT_ISSUED` / `BIL_LINE_ALREADY_CREDITED`, 422 |
| POST | `/api/v1/clinic/bills/{bill_id}/payments` | `PaymentInput` | 201 `Bill` | 404, 409 `BIL_PAYMENT_TOO_LARGE` / `BIL_NOT_ISSUED`, 422 |
| POST | `/api/v1/clinic/bills/{bill_id}/payments/{payment_id}/void` | `VoidInput` | 200 `Bill` | 404, 409 `BIL_VOID_TOO_LATE` / `BIL_ALREADY_VOIDED` / `BIL_VOID_REFUNDED` |
| GET | `/api/v1/clinic/dues?patient_id` | — | 200 `DuesList` | 403 (`COLLECTION_VIEW`) |

Contract 0.43.0 (P1), 0.44.0 (P2), 0.45.0 (P3; the queue entry gains `dues_paise`).

## 6. UI notes
*Settings → Fees* (`/settings/fees`, in the owner's menu): a table of prices by service and
doctor (marking a doctor's own price) that every billing role can read; for owners, one card per
active service (name, kind, default price, each doctor's own price, *Retire*), *Add a service*,
and the retired services with *Restore*. Amounts are typed in rupees (up to two decimals, commas
allowed) and sent as paise; a bad amount is refused in the form before sending. *Directory*
replaces the fee box with *Show the consultation fee publicly*, saying the price and linking to
*Fees*.

*Bills* (`/bills`, owner and front desk; *My bills* for a doctor): the list by state with
balances and *New bill* (pick a patient). A patient's profile lists their bills with *New bill*,
and a completed queue row has *Bill this visit*, which opens the visit's existing bill if it has one.
The bill page edits a draft: lines from the fee schedule (the doctor's price filled in) or
typed, rupees and percents, the bill discount and notes. It has *Save draft*, *Issue bill* and
*Discard draft* (confirmed). An issued bill shows its lines, totals and credit notes. *Correct
this bill* credits chosen lines or cancels the whole bill, with a reason.

*Payments* on an issued bill takes cash, UPI or card (with a reference), starting at the balance.
It offers a refund when a credit note leaves the bill overpaid. Today's payments can be voided with
a reason. *Dues* (`/dues`, owner and front desk) lists who owes. Queue rows show "Dues ₹…", and the
patient's bills show their dues.

## 7. Events and side effects
| Trigger | Audit action | Job enqueued | Analytics event |
|---|---|---|---|
| Service added | `fees.service_added` | — | — |
| Service changed, retired or restored | `fees.service_changed` | — | — |
| Doctor price set or removed | `fees.doctor_price_set` | — | — |
| Bill drafted, changed, discarded | `bill.drafted`, `bill.changed`, `bill.discarded` | — | — |
| Bill issued | `bill.issued` | — | — |
| Credit note issued | `bill.credited` | — | — |
| Payment or refund recorded, voided | `payment.recorded`, `payment.voided` | — | — |

## 8. Edge cases
| Case | Expected outcome |
|---|---|
| A retired service's name is reused | Allowed; restoring the old one then fails with `BIL_SERVICE_NAME_TAKEN` |
| No active consultation service | Every doctor's public fee is null |
| An inactive doctor | Not in the schedule's doctors; their stored prices stay |
| Two owners add the same name at once | One wins; the other gets `BIL_SERVICE_NAME_TAKEN` |
| Two bills issued at the same moment | Consecutive numbers (the clinic row lock) |
| The first bill after 31 March | Numbering restarts at 0001 in the new financial year |
| A cancelled visit bill | The visit may be billed again |
| A 100% bill discount | A total of ₹0; it can still be issued as a record |
| Two payments for the whole balance at once | One is recorded; the other is 409 (R34) |
| A payment voided the next day | 409 `BIL_VOID_TOO_LATE`; use a credit note and a refund |
| A bill fully credited after being paid | `CANCELLED` with a negative balance; refund it |

## 9. Acceptance criteria
- **AC1 (FR-BIL-01, R2)** — Given a clinic created through onboarding, when the owner opens
  *Fees*, then *Consultation* and *Follow-up* are there without prices.
- **AC2 (FR-BIL-01, R3–R6, R9)** — Given the owner, when they price services and set a doctor's own
  price, then the effective prices follow R4, a duplicate active name is 409, a price over
  ₹1,00,000 is 422, and every change is in the audit log.
- **AC3 (R7)** — Given a doctor or the front desk, when they read *Fees*, then they see the
  prices, and any change is 403; another clinic's schedule is never visible.
- **AC4 (FR-BIL-02, R13–R15, R20)** — Given a completed visit and a priced consultation, when the
  front desk bills the visit, then the draft holds the doctor's consultation. A second bill for
  the visit is 409 with the first one's ID, and issuing numbers it `<prefix>/26-27/0001`, then 0002.
- **AC5 (R16–R20)** — Given a draft, when its lines, discounts and notes are replaced, then the
  totals follow R16. Once issued, any change, discard or second issue is 409 `BIL_NOT_DRAFT`.
- **AC6 (FR-BIL-07, R23–R26)** — Given an issued bill, when one line is credited and then the
  rest, then each credit note is numbered `<prefix>/CN/…`, a line cannot be credited twice, the
  bill ends `CANCELLED` with a zero balance, and its visit can be billed again.
- **AC7 (R21)** — Given two doctors, when one drafts and lists bills, then they see only their own.
  Another doctor's bill is 404, and drafting for them is 403 `BIL_NOT_YOURS`.
- **AC8 (R27)** — Given two drafts, when both are issued at once, then they get consecutive numbers.
- **AC9 (FR-BIL-03, R31–R34, R37)** — Given an issued ₹500 bill, when ₹200 cash and then ₹300 UPI
  with a reference are taken, then the balance is settled. Any more is 409 with the most allowed,
  two payments at once never exceed the balance, and each payment is audited.
- **AC10 (R33)** — Given a paid bill, when a line is credited, then a refund up to the credited
  amount is accepted and nothing more.
- **AC11 (R35, R36)** — Given today's payment and a refund taken out of it, when the payment is
  voided, then it is refused until the refund is voided. A payment from an earlier day cannot be voided.
- **AC12 (FR-BIL-05, R39, R40)** — Given patients with partly paid bills, when the desk opens *Dues*,
  then each patient's total appears, largest first. Settled bills and drafts are not counted, a
  doctor is refused (403), another clinic sees none, and the queue row shows the same amount.

## 10. Observability
Log `fees.service_added` with the clinic ID and kind; `bill.drafted` (from a visit or not),
`bill.issued` and `bill.credited` with the clinic ID and amounts. Error codes:
`BIL_SERVICE_NAME_TAKEN`, `BIL_TOO_MANY_SERVICES`, `BIL_NOT_DRAFT`, `BIL_NOT_ISSUED`, `BIL_EMPTY`,
`BIL_LINE_ALREADY_CREDITED`, `BIL_VISIT_BILLED`, `BIL_VISIT_NOT_COMPLETED`, `BIL_NOT_YOURS`,
`BIL_PAYMENT_TOO_LARGE`, `BIL_VOID_TOO_LATE`, `BIL_ALREADY_VOIDED`, `BIL_VOID_REFUNDED`; logs
`payment.recorded` with kind, mode and amount
(docs/ERRORS.md).

## 11. Out of scope
Tax (D3: no GST fields), price history, packages and per-patient discounts (bills, P2).

## 12. Open questions
None for P1.
