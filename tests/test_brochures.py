"""Tests for reading the brochure PDFs into pages."""

import json
from pathlib import Path

import pytest

from sales_assistant.brochures import BrochureError, find_year, read_brochures, save_pages

REAL_BROCHURES = Path(__file__).parents[1] / "data" / "brochures"


def test_read_brochures_tags_each_page_with_brochure_page_and_year(brochures_folder: Path) -> None:
    pages = read_brochures(brochures_folder)

    assert [(page.brochure, page.page_number, page.year) for page in pages] == [
        ("larox-pf-ds", 1, 2025),
        ("larox-pf-ds", 2, 2025),
        ("undated", 1, None),
    ]


def test_read_brochures_keeps_each_printed_line_on_its_own_line(brochures_folder: Path) -> None:
    pages = read_brochures(brochures_folder)

    assert pages[1].text.splitlines() == ["Chambers 8 10 12", "© 2025 Metso"]


def test_read_brochures_names_a_file_that_is_not_a_pdf(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")

    with pytest.raises(BrochureError, match=r"broken\.pdf"):
        read_brochures(tmp_path)


def test_read_brochures_needs_at_least_one_pdf(tmp_path: Path) -> None:
    with pytest.raises(BrochureError, match="No brochure PDFs"):
        read_brochures(tmp_path)


def test_find_year_takes_the_last_copyright_line() -> None:
    assert find_year(["© 2019 a partner's logo", "Back cover", "© 2024 Metso"]) == 2024


def test_save_pages_writes_one_json_object_per_line(brochures_folder: Path, tmp_path: Path) -> None:
    path = tmp_path / "cache" / "pages.jsonl"

    save_pages(read_brochures(brochures_folder), path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["page_number"] for row in rows] == [1, 2, 1]
    assert rows[1]["text"] == "Chambers 8 10 12\n© 2025 Metso"


@pytest.mark.skipif(
    not REAL_BROCHURES.exists(), reason="the assignment data is not in this checkout"
)
def test_real_brochures_keep_spec_table_rows_intact() -> None:
    pages = {(page.brochure, page.page_number): page for page in read_brochures(REAL_BROCHURES)}

    assert len(pages) == 73
    assert len({brochure for brochure, _ in pages}) == 12
    weight_row = "Weight without auxiliary equipment kg 32 000 33 000 35 000 37 000"
    assert weight_row in pages[("larox-pf-ds", 5)].text
    larox_pf_years = {
        pages[("larox-pf-brochure-a", 1)].year,
        pages[("larox-pf-brochure-b", 1)].year,
    }
    assert larox_pf_years == {2021, 2024}
