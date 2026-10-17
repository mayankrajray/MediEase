"""The WeasyPrint renderer (ADR-0012; spec prescriptions R8, R18, R20, AC10; M4-P4).

Real WeasyPrint, real fonts. Text is read back with pdfium, which understands the font encoding
WeasyPrint writes (Devanagari included).
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pypdfium2 as pdfium
import pytest
from weasyprint.urls import FatalURLFetchingError

from mediease_api.adapters.pdf.weasy import ASSETS, AssetsOnlyFetcher, WeasyPrintRenderer
from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.document import RxDocument, build_document
from mediease_api.domain.prescriptions.prescription import Prescription
from tests.builders import new_id
from tests.unit.domain.test_rx_document import issued, patient_of

FONT_SHA256 = {
    "NotoSans-Regular.ttf": "478c558ea716033cd60c03438f628dfa75694dcf6b5f6d505a2f05fd2b4f3823",
    "NotoSans-Bold.ttf": "1df075a380fc7cb898acf64c1f7b3b4dd780de3caa860178bf929de35817a913",
    "NotoSansDevanagari-Regular.ttf": (
        "4e3c66638958c3e2ab5d37f47a8deb89fffeb7be9985c665a519bbc7ba762313"
    ),
    "NotoSansDevanagari-Bold.ttf": (
        "6a09c8d797cfc803d32cdc731e809424d74cbaff59f503de34ade421a08e5bc2"
    ),
    "OFL.txt": "a216f6f8d85c7228093e0ee5e258d9d377e6671f68acb4db1930b29583d0f331",
}

A5 = (419.5, 595.3)
A4 = (595.3, 841.9)


@pytest.fixture(scope="module")
def renderer() -> WeasyPrintRenderer:
    return WeasyPrintRenderer()


def doc_of(rx: Prescription, paper: PaperSize = PaperSize.A5) -> RxDocument:
    return build_document(rx, patient_of(rx), paper_size=paper, timezone="Asia/Kolkata")


def pages_text(pdf: bytes) -> list[str]:
    document = pdfium.PdfDocument(pdf)
    try:
        return [page.get_textpage().get_text_range().replace("\r\n", "\n") for page in document]
    finally:
        document.close()


def page_size(pdf: bytes) -> tuple[float, float]:
    document = pdfium.PdfDocument(pdf)
    try:
        width, height = document[0].get_size()
        return round(width, 1), round(height, 1)
    finally:
        document.close()


def test_vendored_fonts_and_licence_match_their_recorded_hashes() -> None:
    for name, digest in FONT_SHA256.items():
        assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == digest, name


def test_r8_english_sample_with_letterhead_registration_and_footer(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    doc = doc_of(rx)
    pdf = renderer.render(doc)
    assert pdf.startswith(b"%PDF-")
    (text,) = pages_text(pdf)
    assert doc.clinic_name in text and doc.doctor_name in text
    assert rx.doctor_snapshot is not None
    assert f"Reg. No. {rx.doctor_snapshot.registration_number}" in text
    assert "Sample Patient A" in text
    assert "1. Syrup X" in text
    assert "How to give" in text and "Mix in 10 ml of water" in text
    assert "Twice a day, morning and night, after food" in text
    assert "Digitally generated via MediEase" in text
    assert "Page 1 of 1" in text
    assert page_size(pdf) == A5
    assert renderer.last_fetcher is not None and renderer.last_fetcher.refused == []


def test_ac10_hindi_labels_and_phrases_free_text_byte_for_byte(
    renderer: WeasyPrintRenderer,
) -> None:
    """What is laid out is checked exactly; the PDF, as far as its text can be read back.

    Text extraction reorders some Devanagari (the pre-base vowel sign, spacing around
    conjuncts) although the page is drawn correctly (checked by eye in M4-P4), so the PDF
    assertions use strings that read back cleanly.
    """
    rx = issued(Language.HI)
    free_text = "Do not give with milk; 2 चम्मच पानी"
    rx.items = (replace(rx.items[0], warnings=free_text),)
    doc = doc_of(rx)
    html = renderer.html(doc)
    assert '<html lang="hi">' in html
    for hindi in (
        "दवाइयाँ",
        "कैसे दें",
        "10 ml पानी में मिलाएँ",
        "दिन में दो बार, सुबह और रात, खाने के बाद",
        "खोलने के 7 दिन बाद फेंक दें",
        free_text,
    ):
        assert hindi in html, hindi
    pdf = renderer.render(doc)
    (text,) = pages_text(pdf)
    for hindi in ("पंजीकरण सं.", "फ़ोन", "अगली जाँच", "पृष्ठ 1 / 1", "Syrup X", "Do not give with milk"):
        assert hindi in text, hindi


def test_r8_more_than_15_lines_paginate_with_page_numbers(renderer: WeasyPrintRenderer) -> None:
    rx = issued()
    line = rx.items[0]
    rx.items = tuple(
        replace(line, id=new_id(), position=n, medicine_name=f"Medicine {n:02d}")
        for n in range(1, 17)
    )
    texts = pages_text(renderer.render(doc_of(rx)))
    assert len(texts) >= 2
    assert f"Page 1 of {len(texts)}" in texts[0]
    joined = "\n".join(texts)
    assert all(f"{n}. Medicine {n:02d}" in joined for n in range(1, 17))


def test_decision_3a_a4_when_the_clinic_chooses_it(renderer: WeasyPrintRenderer) -> None:
    assert page_size(renderer.render(doc_of(issued(), PaperSize.A4))) == A4


def test_the_same_document_reads_the_same_when_rendered_twice(
    renderer: WeasyPrintRenderer,
) -> None:
    # Bytes can differ (internal font naming); identical downloads come from storing once (R18).
    doc = doc_of(issued())
    assert pages_text(renderer.render(doc)) == pages_text(renderer.render(doc))


def test_markup_and_urls_in_doctor_text_are_printed_as_text_and_fetch_nothing(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    name = '<img src="http://example.invalid/x.png"> Syrup Z'
    notes = "<link rel=stylesheet href=file:///etc/passwd>"
    rx.items = (replace(rx.items[0], medicine_name=name, notes=notes),)
    doc = doc_of(rx)
    assert "&lt;img src=" in renderer.html(doc)
    (text,) = pages_text(renderer.render(doc))
    assert name in text and notes in text
    assert renderer.last_fetcher is not None and renderer.last_fetcher.refused == []


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/font.ttf",
        "https://example.invalid/x.css",
        "file:///etc/passwd",
        (ASSETS / "prescription.css").as_uri(),
        ASSETS.as_uri() + "/../weasy.py",
        "data:text/css,body{}",
    ],
)
def test_the_fetcher_refuses_everything_but_the_vendored_fonts(url: str) -> None:
    fetcher = AssetsOnlyFetcher()
    with pytest.raises(FatalURLFetchingError):
        fetcher.fetch(url)
    assert fetcher.refused == [url]


def test_the_fetcher_serves_a_vendored_font() -> None:
    response = AssetsOnlyFetcher().fetch((ASSETS / "NotoSans-Regular.ttf").as_uri())
    assert response.headers["Content-Type"] == "font/ttf"


def test_a_refused_resource_fails_the_render_as_an_ordinary_error(
    renderer: WeasyPrintRenderer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "mediease_api.adapters.pdf.weasy.FONTS", frozenset({"NotoSans-Regular.ttf"})
    )
    with pytest.raises(RuntimeError, match="refused a resource"):
        renderer.render(doc_of(issued()))


def test_the_pdf_metadata_holds_no_clinical_content(renderer: WeasyPrintRenderer) -> None:
    pdf = renderer.render(doc_of(issued()))
    document = pdfium.PdfDocument(pdf)
    try:
        metadata = {k: v for k, v in document.get_metadata_dict().items() if v}
    finally:
        document.close()
    assert metadata.get("Title") == "Prescription"
    assert set(metadata) <= {"Title", "Producer", "Creator"}


def test_css_strings_keep_the_space_after_an_escaped_character() -> None:
    # CSS eats one whitespace after a hex escape; the footer once lost its word gaps ("सेतैयार").
    from mediease_api.adapters.pdf.weasy import _css_string

    assert str(_css_string("से तैयार")) == '"स\\000947  त\\000948 य\\00093e र"'
    assert str(_css_string('a"b')) == '"a\\000022 b"'


@pytest.mark.parametrize(
    ("language", "first"), [(Language.HI, '"RxDeva"'), (Language.EN, '"RxLatin"')]
)
def test_the_prescriptions_own_script_takes_the_first_font(
    renderer: WeasyPrintRenderer, language: Language, first: str
) -> None:
    """With Latin first, spaces inside Hindi runs collapsed ("के7"); seen in M4-P4."""
    page = renderer._env.get_template("page.css.j2").render(doc=doc_of(issued(language)))
    assert f"html {{ font-family: {first}," in page


def test_m4_p5_every_issued_layout_has_its_template_and_unknown_ones_fail(
    renderer: WeasyPrintRenderer,
) -> None:
    from mediease_api.adapters.pdf.weasy import LAYOUTS
    from mediease_api.domain.prescriptions.prescription import CURRENT_LAYOUT

    assert set(range(1, CURRENT_LAYOUT + 1)) <= set(LAYOUTS)
    doc = doc_of(issued())
    assert doc.layout_version == CURRENT_LAYOUT
    with pytest.raises(ValueError, match="no printed layout 99"):
        renderer.render(replace(doc, layout_version=99))
