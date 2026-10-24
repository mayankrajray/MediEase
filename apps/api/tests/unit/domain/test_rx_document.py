"""What a printed prescription says (spec prescriptions R8, R18, R20; M4-P4)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.patients.patient import Language, Patient, Sex
from mediease_api.domain.prescriptions.document import (
    RxDocument,
    build_document,
    format_phone,
    pdf_object_key,
)
from mediease_api.domain.prescriptions.errors import NotIssued
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    Prescription,
    PrescriptionItem,
)
from mediease_api.domain.prescriptions.schedule import Frequency
from mediease_api.domain.prescriptions.vocabulary import (
    Preparation,
    PreparationCode,
    Storage,
    StorageCode,
    Timing,
)
from tests.builders import a_clinic, a_patient, new_id
from tests.unit.domain.test_prescriptions import TODAY, draft, filled, issue

TZ = "Asia/Kolkata"


def patient_of(rx: Prescription, **overrides: object) -> Patient:
    fields: dict[str, object] = {"id": rx.patient_id, "full_name": "Sample Patient A"}
    fields.update(overrides)
    return a_patient(rx.clinic_id, new_id(), **fields)


def issued(language: Language = Language.EN) -> Prescription:
    rx = filled()
    issue(rx)
    rx.language = language
    return rx


def document(rx: Prescription, **patient: object) -> RxDocument:
    return build_document(rx, patient_of(rx, **patient), paper_size=PaperSize.A5, timezone=TZ)


def details(doc: RxDocument, number: int = 1) -> dict[str, str]:
    return {f.label: f.value for f in doc.medicines[number - 1].details}


def test_r8_the_prd_8_6_sample_reads_as_the_doctor_wrote_it() -> None:
    doc = document(issued())
    medicine = doc.medicines[0]
    assert (medicine.number, medicine.name) == (1, "Syrup X")
    assert details(doc) == {
        "Dose": "5 ml",
        "When": "Twice a day, morning and night, after food",
        "How long": "5 days",
        "How to give": "Shake well before use; Mix in 10 ml of water",
        "Storage": "Throw away 7 days after opening",
    }


def test_r8_letterhead_doctor_patient_date_follow_up_and_footer() -> None:
    rx = issued()
    doc = document(rx, sex=Sex.FEMALE, code="TS-0042")
    assert rx.clinic_snapshot is not None and rx.doctor_snapshot is not None
    assert doc.clinic_name == rx.clinic_snapshot.name
    assert doc.clinic_lines[0] == "1 Sample Road"
    assert doc.clinic_lines[-1].startswith("Phone: +91 ")
    assert doc.doctor_name == rx.doctor_snapshot.display_name
    reg = rx.doctor_snapshot
    assert f"Reg. No. {reg.registration_number}, {reg.registration_council}" in doc.doctor_lines
    assert [(f.label, f.value) for f in doc.patient] == [
        ("Patient", "Sample Patient A"),
        ("Patient code", "TS-0042"),
        ("Age", "36 years"),
        ("Sex", "Female"),
    ]
    assert (doc.issued_on.label, doc.issued_on.value) == ("Date", "19 Oct 2026")
    assert doc.follow_up is not None and doc.follow_up.value == "24 Oct 2026"
    assert [(a.heading, a.entries) for a in doc.advice] == [("Diet", ("plenty of fluids",))]
    assert doc.footer == "Digitally generated via MediEase"
    assert doc.page_label == ("Page ", " of ", "")
    assert (doc.title, doc.revision_note) == ("Prescription", None)


def test_r20_hindi_labels_and_phrases_free_text_verbatim() -> None:
    rx = issued(Language.HI)
    rx.items = (replace(rx.items[0], warnings="Do not give with milk"),)
    doc = document(rx, sex=Sex.MALE)
    assert doc.title == "पर्चा"
    assert doc.medicines_heading == "दवाइयाँ"
    assert doc.medicines[0].name == "Syrup X"
    assert details(doc) == {
        "खुराक": "5 ml",
        "कब लें": "दिन में दो बार, सुबह और रात, खाने के बाद",
        "कितने दिन": "5 दिन",
        "कैसे दें": "इस्तेमाल से पहले अच्छी तरह हिलाएँ; 10 ml पानी में मिलाएँ",
        "कैसे रखें": "खोलने के 7 दिन बाद फेंक दें",
        "सावधानी": "Do not give with milk",
    }
    assert doc.issued_on.value == "19 अक्टूबर 2026"
    assert doc.advice[0].entries == ("plenty of fluids",)
    assert doc.page_label == ("पृष्ठ ", " / ", "")


def test_r8_every_phrase_kind_and_custom_text() -> None:
    rx = issued()
    item = PrescriptionItem.create(
        id=new_id(),
        position=2,
        medicine_name="Tablet Y",
        form="Tablet",
        strength="500 mg",
        frequency=Frequency.CUSTOM,
        frequency_text="Every 6 hours",
        timing=Timing.ANY,
        duration_days=1,
        quantity="10 tablets",
        preparation=[
            Preparation.of(PreparationCode.CUSTOM, "Crush and mix with honey", "p"),
            Preparation.of(PreparationCode.DO_NOT_CRUSH, None, "p"),
        ],
        storage=[
            Storage.of(StorageCode.REFRIGERATE, None, "s"),
            Storage.of(StorageCode.AWAY_FROM_LIGHT, None, "s"),
        ],
        notes="Stop if a rash appears",
    )
    rx.items = (*rx.items, item)
    doc = document(rx)
    assert doc.medicines[1].form_strength == "Tablet · 500 mg"
    assert details(doc, 2) == {
        "When": "Every 6 hours, at any time",
        "How long": "1 day",
        "Quantity": "10 tablets",
        "How to give": "Crush and mix with honey; Swallow whole; do not crush or chew",
        "Storage": "Keep in the fridge; Keep away from light",
        "Notes": "Stop if a rash appears",
    }


def test_r8_timing_alone_starts_with_a_capital() -> None:
    rx = issued()
    rx.items = (replace(rx.items[0], frequency=None, timing=Timing.BEDTIME),)
    assert details(document(rx))["When"] == "At bedtime"


def test_r8_advice_sections_and_notes_and_a_revision() -> None:
    rx = issued()
    rx.advice = Advice.create(
        activity=["Rest for two days"], return_if=["Fever above 102 F"], notes="Drink water"
    )
    rx.version = 3
    rx.follow_up_date = None
    doc = document(rx)
    assert [a.heading for a in doc.advice] == ["Activity", "Come back immediately if"]
    assert doc.advice_notes is not None and doc.advice_notes.value == "Drink water"
    assert doc.revision_note == "Revised prescription (version 3)"
    assert doc.follow_up is None


def test_r8_age_on_the_issue_date_infants_and_undisclosed_sex() -> None:
    rx = issued()
    doc = document(rx, date_of_birth=TODAY - timedelta(days=100), guardian_name="Sample Parent")
    fields = {f.label: f.value for f in doc.patient}
    assert fields["Age"] == "Under 1 year"
    assert "Sex" not in fields  # UNDISCLOSED is not printed


def test_d6_a_draft_is_never_printed() -> None:
    rx = filled(draft())
    with pytest.raises(NotIssued):
        build_document(rx, patient_of(rx), paper_size=PaperSize.A5, timezone=TZ)


def test_superseded_versions_still_have_their_document() -> None:
    rx = issued()
    rx.supersede(rx.updated_at)
    assert document(rx).medicines[0].name == "Syrup X"


def test_r18_one_key_per_version() -> None:
    clinic_id, rx_id = new_id(), new_id()
    assert pdf_object_key(clinic_id, rx_id, 2) == f"rx/{clinic_id}/{rx_id}/v2.pdf"


def test_phone_formatting() -> None:
    assert format_phone("+919876543210") == "+91 98765 43210"
    assert format_phone("+14155550100") == "+14155550100"


def test_paper_size_is_a_clinic_setting_a5_by_default() -> None:
    clinic = a_clinic()
    assert clinic.rx_paper_size is PaperSize.A5
    clinic.update_details(now=clinic.updated_at, rx_paper_size=PaperSize.A4)
    assert clinic.rx_paper_size is PaperSize.A4
    clinic.update_details(now=clinic.updated_at, name="Renamed")
    assert clinic.rx_paper_size is PaperSize.A4  # omitted fields are untouched
