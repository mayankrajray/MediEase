# ADR-0022: Bills are immutable documents, numbered per financial year, corrected by credit notes

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 26 Oct 2026 |
| Deciders | Developer (M6d decisions B3–B5 and D1, and every P2–P7 design, approved in advance, 26 Oct 2026); MediEase engineering |
| Related | ADR-0003 (tenancy); spec `docs/specs/billing.md` R13–R30; M6d milestone decisions B1, B3–B5, D1, D3 |

## Context

A bill is what the patient and the clinic's accountant hold on to. FR-BIL-07 says an issued bill
cannot be edited, and clinics expect gap-free numbers per financial year (D1). Prices change on the
fee schedule (P1). Staff make mistakes at the desk and need to correct them without losing what was
issued. The front desk creates bills but must never see clinical content (PRD §8.1).

## Decision

1. **A bill is a snapshot.** Each line copies the description and the unit price when it is
   drafted, with its own discount and its share of the bill discount. Fee changes never alter a
   bill. Nothing from the visit is copied except its patient and doctor.
2. **Draft, then issued.** A draft can be replaced as a whole or discarded (deleted: it never had
   a number). *Issue* allocates the number and freezes the bill: header and lines never change
   again, enforced in the domain and by a CHECK tying the number to the state.
3. **Numbers per clinic, kind and financial year** (April–March, the clinic-local day of issue):
   `<patient-code prefix>/26-27/0001` for bills and `<prefix>/CN/26-27/0001` for credit notes. The
   next number is `max + 1` of the series, read under the clinic row lock that issuing and crediting
   take first. A unique index (clinic, kind, year, seq) is the last guard. Drafts take no number,
   so the series has no gaps.
4. **Corrections are credit notes.** A credit note is its own numbered document (`kind`
   `CREDIT_NOTE`, always issued). It reverses chosen lines at their final amounts, each at most once
   (a unique index on `credits_line_id`). The bill keeps `credited_paise`. When every line is
   reversed the bill is `CANCELLED`, and its visit may be billed again.
5. **Totals are stored, never recomputed by the screen.** The bill holds the subtotal, discount,
   total, credited, paid and refunded amounts in paise. Its balance is
   `total − credited − paid + refunded`.

## Consequences

- An issued bill is a fixed record, so receipts (P4) can be rendered once per state.
- A wrong bill costs one credit note and a new bill. That is the accountant's expectation, and the
  history stays readable.
- Numbering serialises issuing within one clinic (the clinic row lock), which is acceptable at
  clinic volumes. Other clinics are unaffected.
- No tax fields (D3). Adding GST later means new columns and a new receipt layout, not a change to
  these rules.

## Alternatives rejected

- **Editable bills with a history table.** FR-BIL-07 forbids it, and accountants read the
  document, not the history.
- **One continuous series per clinic.** Indian practice resets per financial year (D1).
- **A Postgres sequence per series.** Sequences leave gaps on rollback, and the clinic lock already
  serialises the allocation.
