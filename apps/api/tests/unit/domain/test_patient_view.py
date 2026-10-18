"""The patient page's content (spec prescriptions R11, R12, R19, R20, §6, AC2; M4-P5)."""

from __future__ import annotations

from dataclasses import replace

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.patient_view import PatientPage, build_patient_view
from mediease_api.domain.prescriptions.prescription import (
    CURRENT_LAYOUT,
    Prescription,
    PrescriptionStatus,
)
from tests.builders import new_id
from tests.unit.domain.test_prescriptions import NOW, draft, filled
from tests.unit.domain.test_rx_document import issued

TZ = "Asia/Kolkata"


def view(chain: list[Prescription], language: Language = Language.EN) -> PatientPage:
    built = build_patient_view(chain, language=language, timezone=TZ)
    assert built is not None
    return built


def fields(v: PatientPage) -> dict[str, str]:
    return {f.label: f.value for f in v.medicines[0].fields}


def test_ac2_the_prd_sample_puts_the_dilution_under_how_to_give() -> None:
    v = view([issued()])
    assert v.medicines[0].name == "Syrup X"
    assert list(fields(v)) == ["How much", "When to take", "How to give", "For how long", "Storage"]
    assert fields(v)["How to give"] == "Shake well before use; Mix in 10 ml of water"
    assert v.updated_note is None and v.version == 1
    assert v.call_label == "Call the clinic" and v.clinic_phone_e164 is not None


def test_r19_r20_hindi_labels_and_the_doctors_text_as_written() -> None:
    rx = issued()
    rx.items = (replace(rx.items[0], warnings="Do not give with milk"),)
    v = view([rx], Language.HI)
    assert v.medicines_heading == "दवाइयाँ"
    assert fields(v)["कब लें"] == "दिन में दो बार, सुबह और रात, खाने के बाद"
    assert fields(v)["सावधानी"] == "Do not give with milk"
    assert v.medicines[0].name == "Syrup X"


def test_r11_the_latest_issued_version_with_the_update_banner() -> None:
    first = issued()
    second = replace(issued(), version=2, id=new_id())
    second.items = (replace(second.items[0], medicine_name="Syrup Y"),)
    first.supersede(NOW)
    v = view([first, second])
    assert (v.version, v.medicines[0].name) == (2, "Syrup Y")
    assert v.updated_note is not None and v.updated_note.startswith("Updated by your doctor on ")


def test_a_chain_with_only_a_draft_has_no_page() -> None:
    assert build_patient_view([filled(draft())], language=Language.EN, timezone=TZ) is None


def test_the_page_leaves_out_the_patients_own_details() -> None:
    rendered = repr(view([issued()])).lower()
    for word in ("patientpage", "patientmedicine"):
        rendered = rendered.replace(word, "")
    assert "sample patient" not in rendered and "patient" not in rendered


def test_m4_p5_issue_fixes_the_current_layout_version() -> None:
    rx = issued()
    assert rx.status is PrescriptionStatus.ISSUED
    assert rx.layout_version == CURRENT_LAYOUT == 1


def test_m4_p6_the_preview_shows_a_draft_as_issuing_today_would() -> None:
    from datetime import date

    import pytest

    from mediease_api.domain.prescriptions.errors import DoctorIncomplete, NotDraft
    from mediease_api.domain.prescriptions.patient_view import build_preview
    from tests.builders import a_clinic, a_doctor

    rx = filled(draft())
    clinic = a_clinic()
    doctor = a_doctor(clinic.id, id=rx.doctor_id)
    page = build_preview(
        rx, doctor=doctor, clinic=clinic, language=Language.HI, today=date(2026, 10, 19)
    )
    assert page.clinic_name == clinic.name and page.doctor_name == doctor.display_name
    assert page.issued_on.value == "19 अक्टूबर 2026" and page.updated_note is None
    assert page.medicines[0].name == "Syrup X"

    with pytest.raises(DoctorIncomplete):
        build_preview(
            rx,
            doctor=replace(doctor, registration_number=" "),
            clinic=clinic,
            language=Language.EN,
            today=date(2026, 10, 19),
        )
    with pytest.raises(NotDraft):
        build_preview(
            issued(), doctor=doctor, clinic=clinic, language=Language.EN, today=date(2026, 10, 19)
        )
