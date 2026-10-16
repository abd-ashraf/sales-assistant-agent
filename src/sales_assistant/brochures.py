"""Read the brochure PDFs into clean pages, each tagged with its brochure, page and year."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import pypdfium2 as pdfium

from sales_assistant.text_cleaning import clean_text

PAGES_FILE = "pages.jsonl"
COPYRIGHT_YEAR = re.compile(r"©\s*(\d{4})")


class BrochureError(Exception):
    """A brochure folder or file that cannot be read."""


@dataclass(frozen=True)
class Page:
    """One brochure page: its file name, page number and year, and its cleaned text."""

    brochure: str
    page_number: int
    year: int | None
    text: str


def read_pdf_text(path: Path) -> list[str]:
    """Return the raw text of each page of the PDF at `path`."""
    try:
        with pdfium.PdfDocument(path) as pdf:
            return [page.get_textpage().get_text_bounded() for page in pdf]
    except pdfium.PdfiumError as error:
        raise BrochureError(f"{path.name} could not be read as a PDF: {error}") from error


def find_year(texts: list[str]) -> int | None:
    """Return the brochure's year from its last © line, or None if it has none."""
    years = COPYRIGHT_YEAR.findall("\n".join(texts))
    return int(years[-1]) if years else None


def build_pages(brochure: str, raw_texts: list[str]) -> list[Page]:
    """Clean each page's text and tag it with its brochure, page number and year."""
    year = find_year(raw_texts)
    return [
        Page(brochure=brochure, page_number=number, year=year, text=clean_text(text))
        for number, text in enumerate(raw_texts, start=1)
    ]


def read_brochures(folder: Path) -> list[Page]:
    """Read every PDF in `folder` into pages, in file-name order."""
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        raise BrochureError(f"No brochure PDFs found in {folder}")
    return [page for pdf in pdfs for page in build_pages(pdf.stem, read_pdf_text(pdf))]


def save_pages(pages: list[Page], path: Path) -> None:
    """Write the pages to `path` as JSON Lines, one page per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for page in pages:
            file.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")
