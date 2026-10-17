"""Prescription rules (FR-RX-01..03, 06, 09; spec R4-R6, R14, R20, AC4; M4-P2 1A-6A). Pure."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.errors import DoctorIncomplete, Empty, NotDraft, Stale
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    LinkDelivery,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    latest_issued,
)
from mediease_api.domain.prescriptions.vocabulary import (
    Frequency,
    Preparation,
    PreparationCode,
    Storage,
    StorageCode,
    Timing,
)
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.visits.visit import Visit, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from tests.builders import a_clinic, a_doctor, new_id

NOW = datetime(2026, 10, 19, 5, 0, tzinfo=UTC)
TODAY = date(2026, 10, 19)


def visit() -> Visit:
    clinic_id = new_id()
    return Visit(
        id=new_id(),
        clinic_id=clinic_id,
        patient_id=new_id(),
        doctor_id=new_id(),
        appointment_id=new_id(),
        status=VisitStatus.OPEN,
        chief_complaint=None,
        findings=None,
        diagnosis=None,
        notes=None,
        vitals=Vitals.empty(),
        revision=1,
        started_at=NOW,
        completed_at=None,
        locked_at=None,
        created_by=new_id(),
        created_at=NOW,
        updated_at=NOW,
    )


def syrup(position: int = 1) -> PrescriptionItem:
    """The PRD §8.6 sample line."""
    return PrescriptionItem.create(
        id=new_id(),
        position=position,
        medicine_name=" Syrup X ",
        dose="5 ml",
        frequency=Frequency.MORNING_NIGHT,
        timing=Timing.AFTER_FOOD,
        duration_days=5,
        preparation=[
            Preparation.of(PreparationCode.SHAKE_WELL, None, "p"),
            Preparation.of(PreparationCode.DILUTE_IN_WATER, "10 ml", "p"),
        ],
        storage=[Storage.of(StorageCode.DISCARD_AFTER_DAYS, 7, "s")],
    )


def draft() -> Prescription:
    return Prescription.first_draft(visit(), id=new_id(), created_by=new_id(), now=NOW)


def filled(rx: Prescription | None = None) -> Prescription:
    rx = rx or draft()
    rx.replace_body(
        items=[syrup()],
        advice=Advice.create(diet=["plenty of fluids", " "]),
        follow_up_date=TODAY + timedelta(days=5),
        seen_revision=rx.revision,
        today=TODAY,
        now=NOW,
    )
    return rx


def issue(rx: Prescription, *, may_message: bool = True, **doctor: object) -> None:
    clinic = a_clinic(address_line="1 Sample Road")
    rx.issue(
        doctor=a_doctor(clinic.id, id=rx.doctor_id, **doctor),
        clinic=clinic,
        language=Language.HI,
        may_message=may_message,
        seen_revision=rx.revision,
        today=TODAY,
        now=NOW + timedelta(minutes=5),
    )


# --- Items and advice (FR-RX-01..03, decision 4A) ------------------------------------------------


def test_fr_rx_01_02_an_item_keeps_the_doctors_words_and_structured_phrases() -> None:
    item = syrup()
    assert (item.medicine_name, item.dose, item.frequency, item.timing, item.duration_days) == (
        "Syrup X",
        "5 ml",
        Frequency.MORNING_NIGHT,
        Timing.AFTER_FOOD,
        5,
    )
    assert [p.as_json() for p in item.preparation] == [
        {"code": "SHAKE_WELL", "text": None},
        {"code": "DILUTE_IN_WATER", "text": "10 ml"},
    ]
    assert item.storage[0].as_json() == {"code": "DISCARD_AFTER_DAYS", "days": 7}


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"medicine_name": "  "}, "items.0.medicine_name"),
        ({"frequency": Frequency.CUSTOM}, "items.0.frequency_text"),
        ({"frequency_text": "every 6 h"}, "items.0.frequency_text"),
        ({"duration_days": 0}, "items.0.duration_days"),
        ({"dose": "x" * 101}, "items.0.dose"),
        (
            {"preparation": [Preparation(PreparationCode.CHEW)] * 2},
            "items.0.preparation",
        ),
    ],
)
def test_items_are_checked_by_field_never_echoing_the_value(
    overrides: dict[str, object], field: str
) -> None:
    fields: dict[str, object] = {"id": new_id(), "position": 1, "medicine_name": "Tab Y"}
    fields.update(overrides)
    with pytest.raises(InvalidValue) as caught:
        PrescriptionItem.create(**fields)  # type: ignore[arg-type]
    assert caught.value.field == field


def test_phrases_take_a_parameter_only_where_it_belongs() -> None:
    with pytest.raises(InvalidValue):
        Preparation.of(PreparationCode.DILUTE_IN_WATER, None, "p")
    with pytest.raises(InvalidValue):
        Preparation.of(PreparationCode.SHAKE_WELL, "now", "p")
    with pytest.raises(InvalidValue):
        Storage.of(StorageCode.DISCARD_AFTER_DAYS, 0, "s")
    with pytest.raises(InvalidValue):
        Storage.of(StorageCode.REFRIGERATE, 3, "s")
    assert Preparation.of(PreparationCode.CUSTOM, " warm it ", "p").text == "warm it"


def test_fr_rx_03_advice_drops_blank_entries_and_bounds_the_lists() -> None:
    advice = Advice.create(return_if=["fever above 102", ""], notes="  ")
    assert (advice.return_if, advice.notes, advice.is_empty) == (("fever above 102",), None, False)
    assert Advice.create().is_empty
    with pytest.raises(InvalidValue):
        Advice.create(diet=["x"] * 11)


# --- Drafts (decision 3A) ------------------------------------------------------------------------


def test_a_draft_is_replaced_whole_from_the_revision_it_was_loaded_at() -> None:
    rx = draft()
    assert (rx.version, rx.status, rx.revision, rx.supersedes_id) == (
        1,
        PrescriptionStatus.DRAFT,
        1,
        None,
    )
    filled(rx)
    assert (len(rx.items), rx.advice.diet, rx.revision) == (1, ("plenty of fluids",), 2)
    with pytest.raises(Stale) as caught:
        rx.replace_body(
            items=[], advice=Advice(), follow_up_date=None, seen_revision=1, today=TODAY, now=NOW
        )
    assert caught.value.details == {"revision": "2"}


def test_positions_items_count_and_follow_up_are_checked() -> None:
    rx = draft()
    for items, follow_up in (
        ([syrup(2)], None),
        ([syrup(i) for i in range(1, 42)], None),
        ([], TODAY),
        ([], TODAY + timedelta(days=366)),
    ):
        with pytest.raises(InvalidValue):
            rx.replace_body(
                items=items,
                advice=Advice(),
                follow_up_date=follow_up,
                seen_revision=1,
                today=TODAY,
                now=NOW,
            )
    assert rx.revision == 1


# --- Issue (R4, R5, R14, R20, AC4, decision 5A) --------------------------------------------------


def test_r5_issuing_freezes_the_draft_with_snapshots_language_and_delivery() -> None:
    rx = filled()
    issue(rx)
    assert (rx.status, rx.issued_at, rx.language, rx.revision) == (
        PrescriptionStatus.ISSUED,
        NOW + timedelta(minutes=5),
        Language.HI,
        3,
    )
    assert rx.doctor_snapshot is not None and rx.doctor_snapshot.qualification == "MBBS"
    assert rx.clinic_snapshot is not None and rx.clinic_snapshot.address_line == "1 Sample Road"
    assert (rx.link_delivery, rx.link_delivery_requested_at) == (
        LinkDelivery.PENDING,
        rx.issued_at,
    )

    with pytest.raises(NotDraft) as caught:
        rx.replace_body(
            items=[], advice=Advice(), follow_up_date=None, seen_revision=3, today=TODAY, now=NOW
        )
    assert caught.value.details == {"status": "ISSUED"}
    with pytest.raises(NotDraft):
        issue(rx)


def test_r14_no_consent_means_no_pending_link() -> None:
    rx = filled()
    issue(rx, may_message=False)
    assert (rx.link_delivery, rx.link_delivery_requested_at) == (LinkDelivery.NOT_CONSENTED, None)


def test_r4_an_empty_prescription_is_not_issued() -> None:
    with pytest.raises(Empty):
        issue(draft())
    advice_only = draft()
    advice_only.replace_body(
        items=[],
        advice=Advice.create(notes="rest"),
        follow_up_date=None,
        seen_revision=1,
        today=TODAY,
        now=NOW,
    )
    issue(advice_only)
    assert advice_only.status is PrescriptionStatus.ISSUED


def test_ac4_a_doctor_without_a_registration_number_cannot_issue() -> None:
    rx = filled()
    clinic = a_clinic()
    doctor = replace(a_doctor(clinic.id, id=rx.doctor_id), registration_number="  ")
    with pytest.raises(DoctorIncomplete) as caught:
        rx.issue(
            doctor=doctor,
            clinic=clinic,
            language=Language.EN,
            may_message=True,
            seen_revision=rx.revision,
            today=TODAY,
            now=NOW,
        )
    assert caught.value.details == {"fields": "registration_number"}
    assert rx.status is PrescriptionStatus.DRAFT


# --- Revise and supersede (R6, FR-RX-09) ---------------------------------------------------------


def test_r6_a_revision_copies_the_content_and_issuing_it_supersedes() -> None:
    v1 = filled()
    issue(v1)
    v2 = Prescription.revision_of(v1, id=new_id(), new_item_id=new_id, created_by=new_id(), now=NOW)
    assert (v2.version, v2.supersedes_id, v2.status, v2.revision) == (
        2,
        v1.id,
        PrescriptionStatus.DRAFT,
        1,
    )
    assert [i.medicine_name for i in v2.items] == ["Syrup X"]
    assert v2.items[0].id != v1.items[0].id
    assert (v2.language, v2.doctor_snapshot, v2.link_delivery) == (None, None, None)
    assert latest_issued([v1, v2]) is v1

    issue(v2)
    v1.supersede(NOW)
    assert (v1.status, v1.link_delivery) == (PrescriptionStatus.SUPERSEDED, LinkDelivery.SUPERSEDED)
    assert latest_issued([v1, v2]) is v2
    with pytest.raises(NotDraft):
        Prescription.revision_of(v1, id=new_id(), new_item_id=new_id, created_by=new_id(), now=NOW)
    with pytest.raises(NotDraft):
        v1.supersede(NOW)


def test_supersede_keeps_a_not_consented_state() -> None:
    rx = filled()
    issue(rx, may_message=False)
    rx.supersede(NOW)
    assert rx.link_delivery is LinkDelivery.NOT_CONSENTED
