"""Fixtures shared by the tests."""

from pathlib import Path

import pytest

from sales_assistant.config import LANGFUSE_SETTINGS

SETTING_NAMES = ("DATA_DIR", "OPENAI_API_KEY", "OPENAI_MODEL", *LANGFUSE_SETTINGS)


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty working directory, with no `.env` and no settings in the environment."""
    monkeypatch.chdir(tmp_path)
    for name in SETTING_NAMES:
        # Set, then delete: pytest then restores the original even if `.env` loading changed it.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return tmp_path


@pytest.fixture
def brochures_folder(tmp_path: Path) -> Path:
    """`data/brochures` with two small PDFs: a dated two-page brochure and an undated one."""
    folder = tmp_path / "data" / "brochures"
    folder.mkdir(parents=True)
    write_pdf(
        folder / "larox-pf-ds.pdf", [["Larox PF-DS"], ["Chambers   8   10   12", "© 2025 Metso"]]
    )
    write_pdf(folder / "undated.pdf", [["A brochure without a copyright line"]])
    return folder


@pytest.fixture
def reports_folder(tmp_path: Path) -> Path:
    """`data/HistoricalServices` with one short field service report."""
    folder = tmp_path / "data" / "HistoricalServices"
    folder.mkdir(parents=True)
    report = "Field Service Report FSR-0001\nOn site 8.4 h, travel 4.9 h\nTotal: EUR 2,215.40\n"
    (folder / "FSR-0001.txt").write_text(report, encoding="utf-8")
    return folder


def write_pdf(path: Path, pages: list[list[str]]) -> None:
    """Write a minimal PDF in Helvetica: one list of text lines per page."""
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for index, lines in enumerate(pages):
        shown = b" 0 -20 Td ".join(b"(" + _pdf_string(line) + b") Tj" for line in lines)
        stream = b"BT /F1 12 Tf 40 760 Td " + shown + b" ET"
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            + f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")

    pdf = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    pdf += f"startxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(pdf)


def _pdf_string(line: str) -> bytes:
    """Encode a line as PDF string content: WinAnsi bytes, with ( ) \\ and non-ASCII escaped."""
    encoded = bytearray()
    for byte in line.encode("cp1252"):
        if byte in b"()\\":
            encoded += b"\\" + bytes([byte])
        elif 32 <= byte < 127:
            encoded.append(byte)
        else:
            encoded += f"\\{byte:03o}".encode()
    return bytes(encoded)
