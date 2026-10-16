"""Tests for the command-line entry point."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sales_assistant.cli import app
from sales_assistant.config import EXPECTED_DATA

runner = CliRunner()


def make_data_folder(root: Path) -> None:
    """Create a `data/` folder holding the three entries the assignment ships."""
    data = root / "data"
    data.mkdir()
    for name in EXPECTED_DATA:
        if name.endswith(".csv"):
            (data / name).touch()
        else:
            (data / name).mkdir()


def test_version_prints_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "sales-assistant 0.1.0" in result.output


def test_check_passes_when_data_and_key_are_present(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_data_folder(workdir)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 0
    assert "missing" not in result.output
    assert "not set" not in result.output


@pytest.mark.usefixtures("workdir")
def test_check_fails_and_names_what_is_missing() -> None:
    result = runner.invoke(app, ["check"])

    assert result.exit_code == 1
    for name in EXPECTED_DATA:
        assert f"missing  {name}" in result.output
    assert "not set" in result.output


def test_check_reads_the_key_from_a_dotenv_file(workdir: Path) -> None:
    make_data_folder(workdir)
    (workdir / ".env").write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 0


@pytest.mark.usefixtures("brochures_folder")
def test_ingest_saves_the_pages_and_lists_each_brochure(workdir: Path) -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "larox-pf-ds" in result.output
    assert "3 pages saved" in result.output
    saved = (workdir / ".cache" / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(saved) == 3


@pytest.mark.usefixtures("workdir")
def test_ingest_stops_with_a_clear_message_when_there_are_no_brochures() -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 1
    assert "No brochure PDFs found" in result.output
