"""WeasyPrint PDF renderer (ADR-0012, spec prescriptions R8, R18; M4-P4).

In-house: no service outside our infrastructure sees a prescription. The document arrives with
every word decided (``domain/prescriptions/document.py``); this adapter only lays it out with a
Jinja2 template (autoescaped, so what the doctor typed is always text, never markup) and the
vendored Noto fonts.

**Nothing is fetched.** WeasyPrint reads resources through a URL fetcher; ours answers only for
the files in ``assets/`` that the stylesheet names and refuses everything else (network, other
local files, ``data:``), stopping the render. Two renders of one document read the same but are
not always byte-identical (internal font naming varies), one more reason a version is rendered
once and its stored file served after that (R18). The PDF's metadata holds only the title
("Prescription") and the producer.

**Layout 3 (M7a-P1, FR-RX-11)** adds the MediEase mark and the verification code with its QR in
the bottom margin. Both are inline SVG (the mark from ``assets/``, the QR drawn here by ``segno``
from the opaque payload), so the fetcher stays closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import segno
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration
from weasyprint.urls import FatalURLFetchingError, URLFetcher, URLFetcherResponse

from mediease_api.domain.billing.receipt import ReceiptDocument
from mediease_api.domain.prescriptions.document import RxDocument

ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = frozenset(
    {
        "NotoSans-Regular.ttf",
        "NotoSans-Bold.ttf",
        "NotoSansDevanagari-Regular.ttf",
        "NotoSansDevanagari-Bold.ttf",
    }
)


class AssetsOnlyFetcher(URLFetcher):  # type: ignore[misc]
    """Serves the vendored fonts from ``assets/``; any other URL stops the render."""

    def __init__(self) -> None:
        super().__init__(allowed_protocols=("file",), allow_redirects=False, fail_on_errors=True)
        self.refused: list[str] = []

    def fetch(self, url: str, headers: Any = None) -> URLFetcherResponse:
        name = _asset_name(url)
        if name is None:
            self.refused.append(url)
            raise FatalURLFetchingError("the prescription renderer fetches no external resources")
        return URLFetcherResponse(url, (ASSETS / name).read_bytes(), {"Content-Type": "font/ttf"})


def _asset_name(url: str) -> str | None:
    prefix = ASSETS.as_uri() + "/"
    if not url.startswith(prefix):
        return None
    name = url[len(prefix) :]
    return name if name in FONTS else None


def _css_string(value: str) -> Markup:
    """A CSS string literal for a phrase (they are ours, but quote them properly anyway).

    Everything but letters, digits and a few punctuation marks becomes a CSS escape, so the
    result is safe in CSS and needs no HTML autoescaping (hence ``Markup``). Each escape ends with
    a space, which CSS consumes as its terminator: without it, a real space after an escaped
    character (a Devanagari vowel sign, say) would be swallowed and two words would join.
    """
    escaped = "".join(
        ch if ch.isalnum() or ch in " .,:/()-" else f"\\{ord(ch):06x} " for ch in value
    )
    return Markup(f'"{escaped}"')


def _qr_svg(payload: str) -> Markup:
    """FR-RX-11: the payload as an inline SVG QR code (error correction M, a 4-module quiet zone).

    ``segno`` escapes nothing because it draws modules, not text; the payload is ours and holds
    only ``MEDIEASE-RX:1:<uuid>``. An empty payload (an earlier layout) draws nothing.
    """
    if not payload:
        return Markup("")
    code = segno.make(payload, error="m", micro=False)
    return Markup(code.svg_inline(border=4, omitsize=True, svgclass="qr", lineclass=None))


@dataclass(frozen=True, slots=True)
class Layout:
    """One printed layout's files (M4-P5). Never edit a released layout: add the next one."""

    html: str
    css: str
    page_css: str


# Layout version -> its files. ``domain.prescriptions.prescription.CURRENT_LAYOUT`` names the
# newest; every version a prescription may have been issued with must stay here.
LAYOUTS: dict[int, Layout] = {
    1: Layout(html="prescription.html.j2", css="prescription.css", page_css="page.css.j2"),
    # M6b-P3 (prescriptions R25): layout 1 plus the Medicine schedule section.
    2: Layout(html="prescription-2.html.j2", css="prescription-2.css", page_css="page.css.j2"),
    # M7a-P1 (FR-RX-11): layout 2 plus the MediEase mark and the verification code with its QR.
    3: Layout(html="prescription-3.html.j2", css="prescription-3.css", page_css="page-3.css.j2"),
}


# M6d-P4 (billing R46): the printed bill. Edit only with the receipt's own state change in mind:
# a stored receipt is never re-rendered, so old files keep the layout they had.
RECEIPT = Layout(html="receipt.html.j2", css="receipt.css", page_css="page.css.j2")


class WeasyPrintRenderer:
    """``PdfRendererPort`` with WeasyPrint. Thread-safe: every render has its own objects."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(ASSETS),
            autoescape=select_autoescape(default=True, default_for_string=True),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["css_string"] = _css_string
        self._env.filters["qr_svg"] = _qr_svg
        self._stylesheets = {
            version: (ASSETS / layout.css).read_text(encoding="utf-8")
            for version, layout in LAYOUTS.items()
        }
        self._receipt_css = (ASSETS / RECEIPT.css).read_text(encoding="utf-8")
        self.last_fetcher: AssetsOnlyFetcher | None = None

    @staticmethod
    def _layout(document: RxDocument) -> Layout:
        layout = LAYOUTS.get(document.layout_version)
        if layout is None:
            raise ValueError(f"no printed layout {document.layout_version}")
        return layout

    def html(self, document: RxDocument) -> str:
        return self._env.get_template(self._layout(document).html).render(doc=document)

    def render(self, document: RxDocument) -> bytes:
        layout = self._layout(document)
        return self._write(
            self.html(document),
            self._stylesheets[document.layout_version],
            self._env.get_template(layout.page_css).render(doc=document),
        )

    def receipt_html(self, document: ReceiptDocument) -> str:
        return self._env.get_template(RECEIPT.html).render(doc=document)

    def render_receipt(self, document: ReceiptDocument) -> bytes:
        """M6d-P4 (billing R46): the bill on the letterhead, the same fonts and fetcher."""
        return self._write(
            self.receipt_html(document),
            self._receipt_css,
            self._env.get_template(RECEIPT.page_css).render(doc=document),
        )

    def _write(self, html_text: str, css_text: str, page: str) -> bytes:
        fetcher = AssetsOnlyFetcher()
        self.last_fetcher = fetcher
        base_url = ASSETS.as_uri() + "/"
        try:  # fonts are fetched while the stylesheets are parsed, so all of it is inside
            fonts = FontConfiguration()
            stylesheets = [
                CSS(
                    string=css,
                    base_url=base_url,
                    url_fetcher=fetcher,
                    font_config=fonts,
                )
                for css in (css_text, page)
            ]
            html = HTML(string=html_text, base_url=base_url, url_fetcher=fetcher)
            pdf: bytes = html.write_pdf(stylesheets=stylesheets, font_config=fonts)
        except FatalURLFetchingError as exc:  # a BaseException: keep it inside the adapter
            raise RuntimeError("the prescription renderer refused a resource") from exc
        return pdf
