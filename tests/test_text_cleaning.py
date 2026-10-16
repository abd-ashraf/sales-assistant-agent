"""Tests for cleaning the text read from PDFs."""

from sales_assistant.text_cleaning import clean_text


def test_clean_text_turns_windows_line_breaks_into_plain_ones() -> None:
    assert clean_text("Larox PF-DS\r\nTower press") == "Larox PF-DS\nTower press"


def test_clean_text_restores_the_hyphen_pdfium_marks_at_a_line_break() -> None:
    assert clean_text("higher air-to\x02pulp ratios") == "higher air-to-pulp ratios"


def test_clean_text_drops_icon_glyphs_and_the_empty_lines_they_leave() -> None:
    assert clean_text("\x1a\x1a\x19\r\nWeight\x1f kg") == "Weight kg"


def test_clean_text_keeps_a_table_row_on_one_line_with_single_spaces() -> None:
    assert clean_text("Chambers   8\t10  12  ") == "Chambers 8 10 12"


def test_clean_text_keeps_trademark_signs_as_printed() -> None:
    assert clean_text("ColumnCell™ and Larox®") == "ColumnCell™ and Larox®"
