"""Patient data requests in SQL (M9-P3; ports/patient_data.py; RUNBOOK §43).

A reviewed tenancy exception (tests/tenancy/test_repository_scoping.py): one reader and writer
over every table that holds the patient's data, so an export misses nothing and an erasure
leaves nothing behind. **Every statement is bound to the clinic and the patient**; table names
in the SQL text are constants of this module, never input.

Erasure keeps the clinical record the clinic must retain (visits, addenda, prescriptions, bills,
payments, reports) under the patient's code, and removes who the patient is: the name, phone,
exact date of birth (the age at registration stays, for the record), guardian and consents;
contact copies (messages, booking requests, staff notification titles); their app links,
reminder choices, dose marks and open links; and scheduled reminders. Issued prescriptions are
immutable and hold no patient details; their stored PDFs did, so those files are removed and
drawn again from the anonymised row on the next download.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from mediease_api.domain.billing.receipt import receipt_object_key
from mediease_api.ports.patient_data import (
    ErasureBlockers,
    ErasureResult,
    PatientRecord,
    PatientRef,
    Row,
)

ERASED_NAME = "Erased patient"
# A valid E.164 form (the domain reads every row) that is not an Indian mobile number.
ERASED_PHONE = "+911000000000"

# Tables with the patient's own ID, exported whole except these columns (secrets and ciphertext).
_BY_PATIENT = (
    "appointments",
    "visits",
    "visit_attachments",
    "prescriptions",
    "bills",
    "payments",
    "reminders",
    "messages",
    "patient_links",
    "patient_account_links",
    "patient_portal_invites",
    "medicine_reminder_prefs",
    "dose_records",
    "booking_requests",
)
# Child tables, through their parent's ID.
_BY_PARENT = (
    ("appointment_status_history", "appointment_id", "appointments"),
    ("visit_addenda", "visit_id", "visits"),
    ("prescription_items", "prescription_id", "prescriptions"),
    ("bill_lines", "bill_id", "bills"),
)
_OMIT = frozenset({"to_phone_encrypted", "token_hash"})
_ACTIVE_VISIT_STATUSES = "('BOOKED', 'ARRIVED', 'IN_CONSULTATION')"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _json(value: Any) -> Any:
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def _rows(result: Any) -> list[Row]:
    return [{k: _json(v) for k, v in row.items() if k not in _OMIT} for row in result.mappings()]


def _age(born: date, on: date) -> int:
    years = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    return max(0, min(120, years))


class SqlAlchemyPatientDataStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _run(self, sql: str, **params: Any) -> Any:
        return self._session.execute(text(sql), params)

    def find(self, clinic_slug: str, code: str) -> PatientRef | None:
        row = self._run(
            "SELECT p.id, p.clinic_id, p.code, c.slug, p.full_name = :erased AS erased"
            " FROM patients p JOIN clinics c ON c.id = p.clinic_id"
            " WHERE c.slug = :slug AND p.code = :code",
            slug=clinic_slug,
            code=code,
            erased=ERASED_NAME,
        ).one_or_none()
        if row is None:
            return None
        return PatientRef(
            clinic_id=row.clinic_id,
            clinic_slug=row.slug,
            patient_id=row.id,
            code=row.code,
            already_erased=bool(row.erased),
        )

    def record(self, ref: PatientRef) -> PatientRecord:
        ids = {"c": ref.clinic_id, "p": ref.patient_id}
        tables: dict[str, Sequence[Row]] = {
            "patient": _rows(
                self._run("SELECT * FROM patients WHERE clinic_id = :c AND id = :p", **ids)
            )
        }
        for table in _BY_PATIENT:
            tables[table] = _rows(
                self._run(
                    f"SELECT * FROM {table} WHERE clinic_id = :c AND patient_id = :p ORDER BY id",
                    **ids,
                )
            )
        for child, key, parent in _BY_PARENT:
            tables[child] = _rows(
                self._run(
                    f"SELECT x.* FROM {child} x JOIN {parent} y ON y.id = x.{key}"
                    " WHERE x.clinic_id = :c AND y.clinic_id = :c AND y.patient_id = :p"
                    " ORDER BY x.id",
                    **ids,
                )
            )
        files: dict[str, str] = {}
        for rx in tables["prescriptions"]:
            if rx.get("pdf_object_key"):
                day = str(rx.get("issued_at") or "draft")[:10]
                files[f"prescriptions/{day}-v{rx['version']}-{rx['id']}.pdf"] = str(
                    rx["pdf_object_key"]
                )
        for report in tables["visit_attachments"]:
            if report.get("deleted_at") is None:
                name = _SAFE_NAME.sub("_", str(report["filename"]))[:80] or "report"
                files[f"reports/{report['id']}-{name}"] = str(report["storage_key"])
        return PatientRecord(tables=tables, files=files)

    def blockers(self, ref: PatientRef, *, today: date) -> ErasureBlockers:
        ids = {"c": ref.clinic_id, "p": ref.patient_id}
        upcoming = self._run(
            "SELECT count(*) FROM appointments a JOIN sessions s ON s.id = a.session_id"
            " WHERE a.clinic_id = :c AND a.patient_id = :p"
            f" AND a.status IN {_ACTIVE_VISIT_STATUSES} AND s.on_date >= :today",
            today=today,
            **ids,
        ).scalar_one()
        open_requests = self._run(
            "SELECT count(*) FROM booking_requests WHERE clinic_id = :c AND patient_id = :p"
            " AND status IN ('PENDING', 'PROPOSED')",
            **ids,
        ).scalar_one()
        return ErasureBlockers(int(upcoming), int(open_requests))

    def erase(self, ref: PatientRef, *, now: datetime) -> ErasureResult:
        ids: dict[str, Any] = {"c": ref.clinic_id, "p": ref.patient_id, "now": now}
        patient = self._run(
            "SELECT full_name, code, date_of_birth, age_years_at_registration, registered_on"
            " FROM patients WHERE clinic_id = :c AND id = :p FOR UPDATE",
            **ids,
        ).one()
        age = patient.age_years_at_registration
        if age is None:
            age = _age(patient.date_of_birth, patient.registered_on)
        first_name = (patient.full_name.split() or ["Patient"])[0][:40]
        counts: dict[str, int] = {}

        def change(what: str, sql: str, **extra: Any) -> None:
            counts[what] = int(self._run(sql, **ids, **extra).rowcount)

        change(
            "patient",
            "UPDATE patients SET full_name = :name, phone_e164 = :phone, guardian_name = NULL,"
            " date_of_birth = NULL, age_years_at_registration = :age, whatsapp_consent = false,"
            " sms_consent = false, opted_out_at = COALESCE(opted_out_at, :now), updated_at = :now"
            " WHERE clinic_id = :c AND id = :p",
            name=ERASED_NAME,
            phone=ERASED_PHONE,
            age=age,
        )
        change(
            "reminders_cancelled",
            "UPDATE reminders SET status = 'CANCELLED', cancelled_at = :now, updated_at = :now,"
            " revision = revision + 1"
            " WHERE clinic_id = :c AND patient_id = :p AND status = 'SCHEDULED'",
        )
        change(
            "messages",
            "UPDATE messages SET to_phone_encrypted = '', updated_at = :now"
            " WHERE clinic_id = :c AND patient_id = :p AND to_phone_encrypted <> ''",
        )
        change(
            "booking_requests",
            "UPDATE booking_requests SET contact_phone = '', age_years = NULL, sex = NULL,"
            " reason = NULL, updated_at = :now WHERE clinic_id = :c AND patient_id = :p",
        )
        change(
            "patient_links_revoked",
            "UPDATE patient_links SET revoked_at = :now, updated_at = :now"
            " WHERE clinic_id = :c AND patient_id = :p AND revoked_at IS NULL",
        )
        change(
            "app_links_revoked",
            "UPDATE patient_account_links SET revoked_at = :now, revoked_by = 'STAFF'"
            " WHERE clinic_id = :c AND patient_id = :p AND revoked_at IS NULL",
        )
        change(
            "app_invites_withdrawn",
            "UPDATE patient_portal_invites SET superseded_at = :now"
            " WHERE clinic_id = :c AND patient_id = :p AND used_at IS NULL"
            " AND superseded_at IS NULL",
        )
        change(
            "reminder_choices",
            "DELETE FROM medicine_reminder_prefs WHERE clinic_id = :c AND patient_id = :p",
        )
        change("dose_records", "DELETE FROM dose_records WHERE clinic_id = :c AND patient_id = :p")
        # Staff notification titles name the patient as "First · CODE" (PatientRef).
        change(
            "notification_titles",
            "UPDATE notifications SET title = replace(title, :was, :erased)"
            " WHERE clinic_id = :c AND strpos(title, :was) > 0",
            was=f"{first_name} · {patient.code}",
            erased=f"Erased · {patient.code}",
        )
        keys = [
            row.pdf_object_key
            for row in self._run(
                "SELECT pdf_object_key FROM prescriptions WHERE clinic_id = :c AND patient_id = :p"
                " AND pdf_object_key IS NOT NULL",
                **ids,
            )
        ]
        keys += self._receipt_keys(ref)
        counts["stored_pdfs"] = len(keys)
        return ErasureResult(counts=counts, blob_keys=keys)

    def _receipt_keys(self, ref: PatientRef) -> list[str]:
        """Every state a receipt of the patient's bills can have had (receipt_state counts credit
        notes, payments and voids, so it is at most their number)."""
        keys: list[str] = []
        bills = self._run(
            "SELECT b.id,"
            " (SELECT count(*) FROM bills c WHERE c.clinic_id = :c AND c.credits_bill_id = b.id)"
            " + (SELECT count(*) * 2 FROM payments p WHERE p.clinic_id = :c AND p.bill_id = b.id)"
            " AS states"
            " FROM bills b WHERE b.clinic_id = :c AND b.patient_id = :p AND b.number IS NOT NULL",
            c=ref.clinic_id,
            p=ref.patient_id,
        )
        for bill in bills:
            keys += [
                receipt_object_key(ref.clinic_id, bill.id, state)
                for state in range(int(bill.states) + 1)
            ]
        return keys
