"""Tests for the agent's tools, called the way the graph's tool step calls them."""

from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage

from sales_assistant.brochures import Page
from sales_assistant.flotation import load_history
from sales_assistant.search import PageIndex
from sales_assistant.tools import make_cost_tool, make_flotation_tool, make_search_tool
from tests.samples import make_record, write_plant_csv

PAGES = [
    Page("larox-pf-ds", 2, 2025, "Chambers 8 10 12"),
    Page("cellstation", 1, None, "Pulp level control in flotation cells"),
]


def run_search(**args: Any) -> ToolMessage:
    """Call search_product_docs as a tool call, and return the message the model gets."""
    search = make_search_tool(PageIndex(PAGES))
    message = search.invoke({"type": "tool_call", "name": search.name, "args": args, "id": "1"})
    assert isinstance(message, ToolMessage)
    return message


def test_search_returns_each_page_under_its_citation_and_year() -> None:
    message = run_search(query="chambers")

    assert message.text == "[larox-pf-ds p.2] (2025)\nChambers 8 10 12"
    assert message.artifact == ["larox-pf-ds p.2"]


def test_search_leaves_out_the_year_when_a_brochure_has_none() -> None:
    assert run_search(query="pulp level").text.startswith("[cellstation p.1]\n")


def test_search_stays_within_the_named_brochures() -> None:
    message = run_search(query="chambers flotation", brochures=["cellstation"])

    assert message.artifact == ["cellstation p.1"]


def test_search_names_an_unknown_brochure_and_lists_the_known_ones() -> None:
    message = run_search(query="chambers", brochures=["larox-pf"])

    assert message.text == "Unknown brochure: larox-pf. Known brochures: cellstation, larox-pf-ds."
    assert message.artifact == []


def test_search_says_when_no_page_matches() -> None:
    message = run_search(query="crusher")

    assert message.text == "No page shares a word with this query."
    assert message.artifact == []


def test_cost_tool_returns_the_estimate_and_the_reports_behind_it() -> None:
    record = make_record("FSR-0027", labour_rate=78, travel_rate=62, travel_hours=4.9)
    cost_tool = make_cost_tool([record])
    args = {
        "equipment": "larox_pf_ds",
        "job_type": "filter_cloth_replacement",
        "country": "Sweden",
        "parts": [{"name": "filter cloth", "quantity": 12}],
    }

    message = cost_tool.invoke(
        {"type": "tool_call", "name": cost_tool.name, "args": args, "id": "1"}
    )

    assert isinstance(message, ToolMessage)
    assert message.text.startswith("Service cost estimate in EUR")
    assert "Typical total: 928." in message.text
    assert message.artifact == ["FSR-0027"]


def test_flotation_tool_returns_the_assessment_and_the_data_it_used(tmp_path: Path) -> None:
    write_plant_csv(tmp_path / "plant.csv")
    flotation_tool = make_flotation_tool(load_history(tmp_path / "plant.csv"))
    args = {"iron_pct": 63.0, "silica_pct": 7.0}

    message = flotation_tool.invoke(
        {"type": "tool_call", "name": flotation_tool.name, "args": args, "id": "1"}
    )

    assert isinstance(message, ToolMessage)
    assert "worse than 75% of the plant's hours" in message.text
    assert message.artifact == ["plant history, 8 hours"]
