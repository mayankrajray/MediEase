"""Clinic applications: the form's rules, certificates and the lifecycle (M6c-P1).

Spec clinic-onboarding R2-R7, R11, R12; ADR-0020.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from mediease_api.domain.onboarding.application import (
    CONFIRM_TTL,
    AlreadyTaken,
    ApplicationInput,
    ApplicationKind,
    ApplicationStatus,
    CheckResult,
    ClinicApplication,
    ConfirmInvalid,
    DoctorCheck,
    DoctorInput,
    NotUnderReview,
    RejectReason,
    format_reference,
    normalise_registration,
    validate,
)
from mediease_api.domain.onboarding.certificate import (
    MAX_CERTIFICATE_BYTES,
    Certificate,
    FileProblem,
    FileRejected,
    certificate_key,
    sniff,
)
from mediease_api.domain.onboarding.lists import COUNCILS, SPECIALTIES, is_council
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)
PDF = b"%PDF-1.4\n% synthetic certificate\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32

DOCTOR = DoctorInput(
    name="Dr. Asha Rao",
    qualification="MBBS, MD",
    council="Maharashtra Medical Council",
    registration_number="mmc 2010 / 12345",
    is_owner=True,
)


def solo(**changes: object) -> ApplicationInput:
    base = ApplicationInput(
        kind=ApplicationKind.SOLO_DOCTOR,
        clinic_name="Sample Family Clinic",
        address_line="12 MG Road",
        city="Pune",
        state="Maharashtra",
        pincode="411001",
        clinic_phone="020 2550 0101",
        specialties=("Family Medicine",),
        owner_name="Asha Rao",
        owner_phone="9000000101",
        owner_email="Owner@Example.test ",
        owner_practises=True,
        doctors=(DOCTOR,),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def clinic(doctors: tuple[DoctorInput, ...], *, practises: bool = False) -> ApplicationInput:
    return solo(kind=ApplicationKind.CLINIC, owner_practises=practises, doctors=doctors)


def staff_doctor(n: int) -> DoctorInput:
    return replace(DOCTOR, name=f"Dr. Staff {n}", registration_number=f"MMC-{n}", is_owner=False)


def submitted(**changes: object) -> ClinicApplication:
    valid = validate(solo())
    application_id = uuid4()
    application = ClinicApplication.submit(
        id=application_id,
        reference="MA-2026-0001",
        application=valid,
        certificates={1: Certificate.of(application_id, 1, PDF)},
        doctor_ids=(uuid4(),),
        now=NOW,
        ip_hash="ip-digest",
    )
    return replace(application, **changes)  # type: ignore[arg-type]


# --- The form (R2-R6) ------------------------------------------------------------------------


def test_fr_onb_01_a_solo_doctor_is_normalised() -> None:
    valid = validate(solo())
    assert valid.owner_email.value == "owner@example.test"
    assert valid.owner_phone.e164 == "+919000000101"
    assert valid.clinic_phone.e164 == "+912025500101"
    assert valid.doctors[0].registration_number == "MMC2010/12345"
    assert (valid.doctors[0].position, valid.doctors[0].is_owner) == (1, True)


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (solo(doctors=(DOCTOR, staff_doctor(2))), "doctors"),
        (solo(owner_practises=False), "doctors.1.is_owner"),
        (clinic(()), "doctors"),
        (clinic(tuple(staff_doctor(n) for n in range(11))), "doctors"),
        (clinic((DOCTOR,), practises=False), "doctors"),
        (clinic((staff_doctor(1),), practises=True), "doctors"),
        (
            clinic((DOCTOR, replace(staff_doctor(2), registration_number="MMC 2010/12345"))),
            "doctors",
        ),
    ],
)
def test_r2_r3_the_doctors_and_the_owner_must_agree(data: ApplicationInput, field: str) -> None:
    with pytest.raises(InvalidValue) as raised:
        validate(data)
    assert raised.value.field.startswith(field)


def test_r5_a_registration_listed_twice_is_refused_on_the_second() -> None:
    twice = clinic(
        (staff_doctor(1), replace(staff_doctor(2), registration_number=" mmc-1 ")), practises=False
    )
    with pytest.raises(InvalidValue) as raised:
        validate(twice)
    assert raised.value.field == "doctors.2.registration_number"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"pincode": "011001"}, "pincode"),
        ({"pincode": "41100"}, "pincode"),
        ({"owner_phone": "02025500101"}, "owner_phone"),
        ({"owner_email": "not-an-email"}, "owner_email"),
        ({"specialties": ()}, "specialties"),
        ({"specialties": ("Astrology",)}, "specialties.0"),
        ({"clinic_name": "  "}, "clinic_name"),
        (
            {"doctors": (replace(DOCTOR, council="Medical Council of Atlantis"),)},
            "doctors.1.council",
        ),
        ({"doctors": (replace(DOCTOR, qualification=""),)}, "doctors.1.qualification"),
        (
            {"doctors": (replace(DOCTOR, registration_number="   "),)},
            "doctors.1.registration_number",
        ),
    ],
)
def test_r4_r6_a_bad_field_is_named(changes: dict[str, object], field: str) -> None:
    with pytest.raises(InvalidValue) as raised:
        validate(solo(**changes))
    assert raised.value.field == field


def test_r4_the_lists_are_published_and_known() -> None:
    assert COUNCILS[0] == "National Medical Commission"
    assert is_council("Delhi Medical Council") and not is_council("delhi medical council")
    assert len(set(SPECIALTIES)) == len(SPECIALTIES)
    assert normalise_registration(" ab 12 ", "f") == "AB12"


# --- Certificates (R7) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(PDF, "application/pdf"), (PNG, "image/png"), (JPEG, "image/jpeg")],
)
def test_r7_the_first_bytes_decide_the_type(data: bytes, content_type: str) -> None:
    assert sniff(data, 1) == content_type


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        (b"", FileProblem.MISSING),
        (None, FileProblem.MISSING),
        (b"MZ\x90\x00 an executable renamed .pdf", FileProblem.TYPE),
        (b"plain text renamed .pdf", FileProblem.TYPE),
        (b"%PDF-" + b"0" * MAX_CERTIFICATE_BYTES, FileProblem.SIZE),
    ],
)
def test_r7_anything_else_is_refused_with_the_position(
    data: bytes | None, problem: FileProblem
) -> None:
    with pytest.raises(FileRejected) as raised:
        sniff(data, 3)
    assert (raised.value.position, raised.value.reason) == (3, problem)
    assert raised.value.details == {"position": "3", "reason": problem.value}


def test_r7_exactly_5_mb_is_accepted_and_hashed() -> None:
    data = b"%PDF-" + b"0" * (MAX_CERTIFICATE_BYTES - 5)
    application_id = uuid4()
    certificate = Certificate.of(application_id, 2, data)
    assert certificate.size == MAX_CERTIFICATE_BYTES
    assert (
        certificate.key
        == certificate_key(application_id, 2)
        == (f"applications/{application_id}/doctor-2")
    )
    assert len(certificate.sha256) == 64


# --- Lifecycle (R9, R11, R12, R15) -----------------------------------------------------------


def test_r9_a_submission_is_pending_and_unconfirmed() -> None:
    application = submitted()
    assert application.status is ApplicationStatus.PENDING
    assert not application.is_confirmed and application.confirm_digest is None
    assert application.confirm_expires_at == NOW + CONFIRM_TTL
    assert application.doctors[0].certificate is not None and application.doctors[0].id


def test_r11_r12_the_link_confirms_once_and_only_in_time() -> None:
    linked = submitted().with_confirm_digest("digest-1", now=NOW)
    confirmed = linked.confirm(now=NOW + timedelta(hours=1))
    assert confirmed.is_confirmed and confirmed.confirm_digest is None
    with pytest.raises(ConfirmInvalid):
        confirmed.confirm(now=NOW + timedelta(hours=2))
    with pytest.raises(ConfirmInvalid):
        linked.confirm(now=NOW + CONFIRM_TTL)
    with pytest.raises(ConfirmInvalid):
        submitted().confirm(now=NOW)  # no link was ever sent
    with pytest.raises(InvalidTransition):
        confirmed.with_confirm_digest("digest-2", now=NOW)


def test_r27_r33_r41_the_review_transitions() -> None:
    reviewer = uuid4()
    with pytest.raises(InvalidTransition):
        submitted().start_review(reviewer_id=reviewer, now=NOW)
    confirmed = submitted().with_confirm_digest("d", now=NOW).confirm(now=NOW)
    reviewing = confirmed.start_review(reviewer_id=reviewer, now=NOW)
    assert (reviewing.status, reviewing.taken_by) == (ApplicationStatus.UNDER_REVIEW, reviewer)
    with pytest.raises(AlreadyTaken):
        reviewing.start_review(reviewer_id=uuid4(), now=NOW)
    rejected = reviewing.reject(
        reviewer_id=reviewer, reason=RejectReason.CERTIFICATE_UNCLEAR, message=None, now=NOW
    )
    assert (rejected.status, rejected.decision_reason) == (
        ApplicationStatus.REJECTED,
        RejectReason.CERTIFICATE_UNCLEAR,
    )
    with pytest.raises(InvalidValue):
        reviewing.reject(reviewer_id=reviewer, reason=RejectReason.OTHER, message=" ", now=NOW)
    with pytest.raises(NotUnderReview):
        confirmed.reject(reviewer_id=reviewer, reason=RejectReason.DUPLICATE, message=None, now=NOW)
    doctor = reviewing.doctors[0]
    assert doctor.id is not None and reviewing.doctor(doctor.id) == doctor
    with pytest.raises(InvalidValue):
        reviewing.approve(reviewer_id=reviewer, clinic_id=uuid4(), verified=set(), now=NOW)
    clinic_id = uuid4()
    approved = reviewing.approve(
        reviewer_id=reviewer, clinic_id=clinic_id, verified={doctor.id}, now=NOW
    )
    assert (approved.status, approved.clinic_id) == (ApplicationStatus.APPROVED, clinic_id)


def test_r30_verified_needs_both_checks() -> None:
    with pytest.raises(InvalidValue):
        DoctorCheck.record(
            doctor_id=uuid4(),
            checked_by=uuid4(),
            now=NOW,
            register_checked=True,
            certificate_matches=False,
            result=CheckResult.VERIFIED,
            note=None,
        )
    check = DoctorCheck.record(
        doctor_id=uuid4(),
        checked_by=uuid4(),
        now=NOW,
        register_checked=True,
        certificate_matches=False,
        result=CheckResult.NOT_VERIFIED,
        note="  name differs  ",
    )
    assert check.note == "name differs"


def test_r17_duplicates_are_remembered_once_each() -> None:
    application = submitted(duplicate_of=())
    assert not application.possible_duplicate
    valid = validate(solo())
    flagged = ClinicApplication.submit(
        id=uuid4(),
        reference="MA-2026-0002",
        application=valid,
        certificates={1: Certificate.of(uuid4(), 1, PDF)},
        doctor_ids=(uuid4(),),
        now=NOW,
        ip_hash=None,
        duplicate_of=("MA-2026-0001", "MA-2026-0001", "clinic:x"),
    )
    assert flagged.duplicate_of == ("MA-2026-0001", "clinic:x") and flagged.possible_duplicate


def test_r9_references_have_at_least_four_digits() -> None:
    assert format_reference(2026, 42) == "MA-2026-0042"
    assert format_reference(2026, 12345) == "MA-2026-12345"
