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


# Layout 1's files as released (M4-P5). A version issued on it must print as it was issued, so
# they are never edited: a change goes into the next layout (M6b-P3 added layout 2).
LAYOUT_1_SHA256 = {
    "prescription.html.j2": "f0ac1841ffa6a3b64f1d480eef0d161ba107d8ec2d6b6ceec9c3bfb7b5e4684e",
    "prescription.css": "e69d98e26fda30e24a0e84944ef01f0620017e814f8c5fc761a3b4e9a23ac767",
    "page.css.j2": "fee9e443941cb1faf800b5cddd2bde9d7a031fe3ad73fe0f17af883407928fad",
}


def test_m6b_p3_layout_1_files_are_unchanged() -> None:
    for name, digest in LAYOUT_1_SHA256.items():
        assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == digest, name


def test_r25_layout_2_prints_the_medicine_schedule_and_layout_1_does_not(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    new = "\n".join(pages_text(renderer.render(doc_of(rx))))
    assert "Medicine schedule" in new and "Morning" in new and "Night" in new
    old = "\n".join(pages_text(renderer.render(doc_of(replace(rx, layout_version=1)))))
    assert "Medicine schedule" not in old
    # The rest of the prescription reads the same on both layouts.
    assert "Syrup X" in old and "Syrup X" in new


# Layout 2's files as released (M6b-P3). Frozen like layout 1 when layout 3 arrived (M7a-P1).
LAYOUT_2_SHA256 = {
    "prescription-2.html.j2": "bd41c81b3ff220ee53ee1e6c7c8f4c72479f10b327686e7c2a889f4a83b2ebc0",
    "prescription-2.css": "3aec98c84c18ebd1cde217264bc042cd70258f4d9bae47593d7ac1bcd576e5b6",
}


def test_m7a_p1_layout_2_files_are_unchanged() -> None:
    for name, digest in LAYOUT_2_SHA256.items():
        assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == digest, name


# --- Layout 3: the MediEase layer (M7a-P1, FR-RX-11, ADR-0023) ------------------------------


def qr_texts(pdf: bytes, *, scale: float = 3) -> list[list[str]]:
    """Every page rasterised (scale 3 = 216 dpi) and its QR codes decoded with zxing-cpp."""
    import zxingcpp

    document = pdfium.PdfDocument(pdf)
    try:
        return [
            [code.text for code in zxingcpp.read_barcodes(page.render(scale=scale).to_pil())]
            for page in document
        ]
    finally:
        document.close()


@pytest.mark.parametrize("paper", [PaperSize.A5, PaperSize.A4])
@pytest.mark.parametrize("language", [Language.EN, Language.HI])
def test_fr_rx_11_layout_3_prints_the_code_and_a_qr_that_decodes_to_the_version(
    renderer: WeasyPrintRenderer, paper: PaperSize, language: Language
) -> None:
    rx = issued(language)
    pdf = renderer.render(doc_of(rx, paper))
    (text,) = pages_text(pdf)
    assert str(rx.id) in text
    assert ("सत्यापन कोड" if language is Language.HI else "Verification code") in text
    assert qr_texts(pdf) == [[f"MEDIEASE-RX:1:{rx.id}"]]
    assert renderer.last_fetcher is not None and renderer.last_fetcher.refused == []


def test_fr_rx_11_the_block_is_on_every_page_of_a_long_prescription(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    line = rx.items[0]
    rx.items = tuple(
        replace(line, id=new_id(), position=n, medicine_name=f"Medicine {n:02d}")
        for n in range(1, 17)
    )
    pdf = renderer.render(doc_of(rx))
    texts = pages_text(pdf)
    assert len(texts) >= 2
    assert all(str(rx.id) in t and "Digitally generated via MediEase" in t for t in texts)
    assert qr_texts(pdf) == [[f"MEDIEASE-RX:1:{rx.id}"]] * len(texts)


def test_fr_rx_11_the_qr_holds_only_the_opaque_payload_no_patient_or_clinical_text(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    doc = doc_of(rx)
    ((payload,),) = qr_texts(renderer.render(doc))
    assert payload == f"MEDIEASE-RX:1:{rx.id}"
    for private in ("Sample Patient A", "Syrup X", doc.clinic_name, doc.doctor_name):
        assert private not in payload


def test_fr_rx_11_doctor_text_cannot_reach_the_verification_block(
    renderer: WeasyPrintRenderer,
) -> None:
    rx = issued()
    rx.items = (replace(rx.items[0], notes='</div><div class="verify">MEDIEASE-RX:1:forged'),)
    html = renderer.html(doc_of(rx))
    assert html.count('class="verify"') == 1
    assert qr_texts(renderer.render(doc_of(rx))) == [[f"MEDIEASE-RX:1:{rx.id}"]]


def test_fr_rx_11_layouts_1_and_2_print_no_code_or_qr(renderer: WeasyPrintRenderer) -> None:
    rx = issued()
    for layout in (1, 2):
        pdf = renderer.render(doc_of(replace(rx, layout_version=layout)))
        assert str(rx.id) not in "\n".join(pages_text(pdf))
        assert qr_texts(pdf) == [[]]
