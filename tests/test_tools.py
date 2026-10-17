"""Tests for the agent's tools, called the way the graph's tool step calls them."""

from typing import Any

from langchain_core.messages import ToolMessage

from sales_assistant.brochures import Page
from sales_assistant.search import PageIndex
from sales_assistant.tools import make_search_tool

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
