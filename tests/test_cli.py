"""Tests for the command-line entry point."""

import io
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from typer.testing import CliRunner

from sales_assistant import cli, tracing
from sales_assistant.brochures import PAGES_FILE, Page, save_pages
from sales_assistant.cli import app, use_utf8_output
from sales_assistant.config import EXPECTED_DATA, FLOTATION_CSV
from sales_assistant.product_cards import CARDS_FILE, ProductCard, load_cards, save_cards
from sales_assistant.service_records import (
    RECORDS_FILE,
    CostStatus,
    Equipment,
    JobType,
    ReportReading,
    load_records,
    save_records,
)
from tests.fakes import (
    ScriptedChatModel,
    TurnRecorder,
    never_answering_model,
    scripted_model,
    tool_call,
)
from tests.samples import make_record, write_plant_csv

runner = CliRunner()
LANGFUSE_URL = "http://localhost:3000"


def make_data_folder(root: Path) -> None:
    """Create a `data/` folder holding the three entries the assignment ships."""
    data = root / "data"
    data.mkdir()
    for name in EXPECTED_DATA:
        if name.endswith(".csv"):
            (data / name).touch()
        else:
            (data / name).mkdir()


def set_up_langfuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the three Langfuse settings in the environment; no Langfuse server answers there."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", LANGFUSE_URL)


def use_model(monkeypatch: pytest.MonkeyPatch, model: ScriptedChatModel) -> ScriptedChatModel:
    """Make the commands use `model` instead of the OpenAI model."""
    monkeypatch.setattr(cli, "chat_model", lambda _settings: model)
    return model


def description(product: str) -> AIMessage:
    """The model's reply to a request for a product card."""
    return tool_call("ProductDescription", product=product, category="filter", summary="Filters.")


def reading(customer: str) -> AIMessage:
    """The model's reply to a request to read a service report: a total, without lines."""
    form = ReportReading(
        customer=customer,
        site="Aitik",
        country="Sweden",
        visit_date="2023-05-12",
        equipment=Equipment.LAROX_PF_DS,
        job_types=[JobType.FILTER_CLOTH_REPLACEMENT],
        on_site_hours=8.4,
        travel_hours=4.9,
        task_hours=[],
        currency="EUR",
        cost_lines=[],
        total=2215.4,
        vat=None,
        weekend=False,
        emergency=False,
        customer_parts=False,
    )
    return tool_call("ReportReading", **form.model_dump(mode="json"))


@pytest.fixture(name="prepared")
def fixture_prepared(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with a page, its product card and a service record, and a key set."""
    save_pages([Page("larox-pf-ds", 2, 2025, "Chambers 8 10 12")], workdir / ".cache" / PAGES_FILE)
    card = ProductCard("larox-pf-ds", 2025, "Larox PF-DS", "tower press filter", "Filters.")
    save_cards([card], workdir / ".cache" / CARDS_FILE)
    record = make_record("FSR-0027", labour_rate=78, travel_rate=62, travel_hours=4.9)
    save_records([record], workdir / ".cache" / RECORDS_FILE)
    write_plant_csv(workdir / "data" / FLOTATION_CSV)
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
    assert "OpenAI key: set" in result.output
    assert "Langfuse: not set (optional" in result.output


@pytest.mark.parametrize(
    ("problem", "exit_code", "shown"),
    [(None, 0, f"Langfuse: ok at {LANGFUSE_URL}"), ("not reachable", 1, "Langfuse: not reachable")],
)
def test_check_tests_langfuse_when_it_is_set_up(
    workdir: Path,
    monkeypatch: pytest.MonkeyPatch,
    problem: str | None,
    exit_code: int,
    shown: str,
) -> None:
    make_data_folder(workdir)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    set_up_langfuse(monkeypatch)
    monkeypatch.setattr(cli, "langfuse_problem", lambda: problem)

    result = runner.invoke(app, ["check"])

    assert result.exit_code == exit_code
    assert shown in result.output


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
def test_ingest_without_a_key_saves_the_pages_and_says_what_was_not_written(
    workdir: Path,
) -> None:
    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "Product cards and service records not written: set OPENAI_API_KEY" in result.output
    assert not (workdir / ".cache" / CARDS_FILE).exists()
    assert not (workdir / ".cache" / RECORDS_FILE).exists()


@pytest.mark.usefixtures("brochures_folder", "reports_folder")
def test_ingest_with_a_key_writes_the_product_cards_and_the_service_records(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    replies = (description("Larox PF-DS"), description("Undated"), reading("Boliden AB"))
    use_model(monkeypatch, scripted_model(*replies))

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 0
    assert "2 product cards saved" in result.output
    assert "1 service records saved" in result.output
    cards = load_cards(workdir / ".cache" / CARDS_FILE)
    assert [(card.brochure, card.product) for card in cards] == [
        ("larox-pf-ds", "Larox PF-DS"),
        ("undated", "Undated"),
    ]
    records = load_records(workdir / ".cache" / RECORDS_FILE)
    assert [(record.report_id, record.cost_status) for record in records] == [
        ("FSR-0001", CostStatus.TOTAL_ONLY)
    ]


@pytest.mark.usefixtures("brochures_folder", "reports_folder")
def test_ingest_keeps_what_the_model_wrote_unless_asked_to_rewrite_it(
    workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    first = (description("First name"), description("Undated"), reading("First customer"))
    use_model(monkeypatch, scripted_model(*first))
    runner.invoke(app, ["ingest"])

    use_model(monkeypatch, scripted_model())
    kept = runner.invoke(app, ["ingest"])
    again = (description("New name"), description("Undated"), reading("New customer"))
    use_model(monkeypatch, scripted_model(*again))
    rewritten = runner.invoke(app, ["ingest", "--rewrite"])

    assert kept.exit_code == rewritten.exit_code == 0
    assert "First name" in kept.output
    assert "New name" in rewritten.output
    assert load_cards(workdir / ".cache" / CARDS_FILE)[0].product == "New name"
    assert load_records(workdir / ".cache" / RECORDS_FILE)[0].customer == "New customer"


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


@pytest.mark.usefixtures("prepared")
def test_chat_traces_each_turn_under_one_langfuse_session(monkeypatch: pytest.MonkeyPatch) -> None:
    set_up_langfuse(monkeypatch)
    recorder = TurnRecorder()
    monkeypatch.setattr(tracing, "CallbackHandler", lambda: recorder)
    use_model(monkeypatch, scripted_model("First answer.", "Second answer."))

    result = runner.invoke(app, ["chat"], input="First question\nSecond question\nexit\n")

    assert result.exit_code == 0
    assert len(recorder.turns) == 2
    assert {turn["langfuse_trace_name"] for turn in recorder.turns} == {"chat"}
    chat_thread = recorder.turns[0]["thread_id"]
    assert {turn["langfuse_session_id"] for turn in recorder.turns} == {chat_thread}


def test_ask_asks_for_ingest_when_the_service_records_are_missing(prepared: Path) -> None:
    (prepared / ".cache" / RECORDS_FILE).unlink()

    result = runner.invoke(app, ["ask", "What should I budget?"])

    assert result.exit_code == 1
    assert "No service records" in result.output


@pytest.mark.usefixtures("prepared")
def test_ask_shows_the_cost_tool_call_and_the_reports_behind_the_estimate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estimate = tool_call(
        "estimate_service_cost",
        equipment="larox_pf_ds",
        job_type="filter_cloth_replacement",
        country="Sweden",
        parts=[],
    )
    use_model(monkeypatch, scripted_model(estimate, "Budget about EUR 960 [FSR-0027]."))

    result = runner.invoke(app, ["ask", "What does a cloth change in Sweden cost?"])

    assert result.exit_code == 0
    assert "→ estimate_service_cost(equipment='larox_pf_ds'" in result.output
    assert "← FSR-0027" in result.output
    assert "Budget about EUR 960 [FSR-0027]." in result.output


@pytest.mark.usefixtures("prepared")
def test_estimate_prints_what_the_cost_tool_gives_without_the_model() -> None:
    result = runner.invoke(
        app,
        ["estimate", "larox_pf_ds", "filter_cloth_replacement", "Sweden", "--part", "cloth"],
    )

    assert result.exit_code == 0
    assert "Service cost estimate in EUR" in result.output
    assert "no invoice price for cloth on larox_pf_ds" in result.output


@pytest.mark.usefixtures("workdir")
def test_estimate_asks_for_ingest_when_there_are_no_records() -> None:
    result = runner.invoke(app, ["estimate", "larox_pf_ds", "filter_cloth_replacement", "Chile"])

    assert result.exit_code == 1
    assert "No service records" in result.output


@pytest.mark.usefixtures("prepared")
def test_assess_prints_what_the_flotation_tool_gives_without_the_model() -> None:
    result = runner.invoke(app, ["assess", "63", "7"])

    assert result.exit_code == 0
    assert "Silica 7.00%: the plant's median is 4.50%" in result.output


@pytest.mark.usefixtures("prepared")
def test_assess_refuses_readings_that_are_not_percentages() -> None:
    result = runner.invoke(app, ["assess", "120", "3.1"])

    assert result.exit_code == 1
    assert "between 0 and 100" in result.output


@pytest.mark.usefixtures("workdir")
def test_assess_names_the_missing_plant_data() -> None:
    result = runner.invoke(app, ["assess", "64.5", "3.1"])

    assert result.exit_code == 1
    assert "No plant data" in result.output


@pytest.mark.usefixtures("prepared")
def test_ask_shows_the_flotation_tool_call_and_the_data_it_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = tool_call("assess_flotation_readings", iron_pct=63.0, silica_pct=7.0)
    use_model(monkeypatch, scripted_model(readings, "Worse than 75% of the plant's hours."))

    result = runner.invoke(app, ["ask", "63% iron and 7% silica: is that normal?"])

    assert result.exit_code == 0
    assert "→ assess_flotation_readings(iron_pct=63.0, silica_pct=7.0)" in result.output
    assert "← plant history, 8 hours" in result.output
