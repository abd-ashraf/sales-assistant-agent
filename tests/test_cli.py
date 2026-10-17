"""Tests for the command-line entry point."""

import io
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from sales_assistant import cli
from sales_assistant.brochures import PAGES_FILE, Page, save_pages
from sales_assistant.cli import app, use_utf8_output
from sales_assistant.config import EXPECTED_DATA
from sales_assistant.product_cards import CARDS_FILE, ProductCard, load_cards, save_cards
from tests.fakes import ScriptedChatModel, never_answering_model, scripted_model, tool_call

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


def use_model(monkeypatch: pytest.MonkeyPatch, model: ScriptedChatModel) -> ScriptedChatModel:
    """Make the commands use `model` instead of the OpenAI model."""
    monkeypatch.setattr(cli, "chat_model", lambda _settings: model)
    return model


def description(product: str) -> AIMessage:
    """The model's reply to a request for a product card."""
    return tool_call("ProductDescription", product=product, category="filter", summary="Filters.")


@pytest.fixture(name="prepared")
def fixture_prepared(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with one page and its product card prepared, and a key set."""
    save_pages([Page("larox-pf-ds", 2, 2025, "Chambers 8 10 12")], workdir / ".cache" / PAGES_FILE)
    card = ProductCard("larox-pf-ds", 2025, "Larox PF-DS", "tower press filter", "Filters.")
    save_cards([card], workdir / ".cache" / CARDS_FILE)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return workdir


def test_use_utf8_output_lets_a_legacy_code_page_stream_print_any_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(written, encoding="cp1252", newline="\n"))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))

    use_utf8_output()
    print("10 - 45 μm")
    sys.stdout.flush()

    assert written.getvalue().decode("utf-8") == "10 - 45 μm\n"


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


@pytest.mark.usefixtures("brochures_folder")
def test_ingest_without_a_key_saves_the_pages_and_says_the_cards_were_not_written(
    workdir: Path,
) -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "Product cards not written: set OPENAI_API_KEY" in result.output
    assert not (workdir / ".cache" / CARDS_FILE).exists()


@pytest.mark.usefixtures("brochures_folder")
def test_ingest_with_a_key_has_the_model_write_a_card_per_brochure(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    use_model(monkeypatch, scripted_model(description("Larox PF-DS"), description("Undated")))

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "2 product cards saved" in result.output
    cards = load_cards(workdir / ".cache" / CARDS_FILE)
    assert [(card.brochure, card.product) for card in cards] == [
        ("larox-pf-ds", "Larox PF-DS"),
        ("undated", "Undated"),
    ]


@pytest.mark.usefixtures("brochures_folder")
def test_ingest_keeps_saved_cards_unless_asked_to_rewrite_them(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    use_model(monkeypatch, scripted_model(description("First name"), description("Undated")))
    runner.invoke(app, ["ingest"])

    use_model(monkeypatch, scripted_model())
    kept = runner.invoke(app, ["ingest"])
    use_model(monkeypatch, scripted_model(description("New name"), description("Undated")))
    rewritten = runner.invoke(app, ["ingest", "--rewrite-cards"])

    assert "First name" in kept.output
    assert "New name" in rewritten.output
    assert load_cards(workdir / ".cache" / CARDS_FILE)[0].product == "New name"


@pytest.mark.usefixtures("workdir")
def test_ingest_stops_with_a_clear_message_when_there_are_no_brochures() -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 1
    assert "No brochure PDFs found" in result.output


@pytest.mark.usefixtures("workdir")
def test_search_asks_for_ingest_first() -> None:
    result = runner.invoke(app, ["search", "chambers"])

    assert result.exit_code == 1
    assert "run `sales-assistant ingest` first" in result.output


@pytest.mark.usefixtures("workdir", "brochures_folder")
def test_search_shows_the_best_matching_page_after_ingest() -> None:
    runner.invoke(app, ["ingest"])

    result = runner.invoke(app, ["search", "chambers"])

    assert result.exit_code == 0
    assert "larox-pf-ds p.2" in result.output
    assert "Chambers 8 10 12" in result.output


@pytest.mark.usefixtures("workdir", "brochures_folder")
def test_search_names_an_unknown_brochure() -> None:
    runner.invoke(app, ["ingest"])

    result = runner.invoke(app, ["search", "chambers", "--brochure", "no-such-brochure"])

    assert result.exit_code == 1
    assert "Unknown brochure: no-such-brochure" in result.output


@pytest.mark.usefixtures("workdir")
def test_ask_needs_the_api_key() -> None:
    result = runner.invoke(app, ["ask", "How many chambers?"])

    assert result.exit_code == 1
    assert "OPENAI_API_KEY is not set" in result.output


def test_ask_asks_for_ingest_when_the_product_cards_are_missing(prepared: Path) -> None:
    (prepared / ".cache" / CARDS_FILE).unlink()

    result = runner.invoke(app, ["ask", "How many chambers?"])

    assert result.exit_code == 1
    assert "No product cards" in result.output


@pytest.mark.usefixtures("prepared")
def test_ask_shows_each_tool_call_and_the_pages_it_found_then_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = tool_call("search_product_docs", query="chambers", brochures=["larox-pf-ds"])
    use_model(monkeypatch, scripted_model(search, "From 8 to 12 [larox-pf-ds p.2]."))

    result = runner.invoke(app, ["ask", "How many chambers can a PF-DS have?"])

    assert result.exit_code == 0
    assert "→ search_product_docs(query='chambers', brochures=['larox-pf-ds'])" in result.output
    assert "← larox-pf-ds p.2" in result.output
    assert "From 8 to 12 [larox-pf-ds p.2]." in result.output
    assert "model calls: 2" in result.output


@pytest.mark.usefixtures("prepared")
def test_ask_says_so_when_the_step_cap_stops_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    use_model(monkeypatch, never_answering_model("search_product_docs", query="chambers"))

    result = runner.invoke(app, ["ask", "How many chambers?"])

    assert result.exit_code == 1
    assert "Stopped after 12 steps without an answer" in result.output


@pytest.mark.usefixtures("prepared")
def test_chat_keeps_the_conversation_until_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    model = use_model(monkeypatch, scripted_model("Which Larox model?", "Then the PF-DS fits."))

    result = runner.invoke(app, ["chat"], input="Our filter is slow\nA PF-DS\nexit\n")

    assert result.exit_code == 0
    assert "Then the PF-DS fits." in result.output
    assert [message.text for message in model.received[1][1:]] == [
        "Our filter is slow",
        "Which Larox model?",
        "A PF-DS",
    ]
