"""Tests for the system prompt."""

from sales_assistant.product_cards import ProductCard
from sales_assistant.prompts import system_prompt

CARDS = [
    ProductCard("larox-pf-brochure-a", 2021, "Larox PF", "pressure filter", "Older words."),
    ProductCard("larox-pf-brochure-b", 2024, "Larox PF", "pressure filter", "Newer words."),
    ProductCard("undated", None, "Undated filter", "filter", "Filters."),
    ProductCard("cellstation", 2023, "CellStation", "flotation control", "Controls levels."),
]


def test_system_prompt_ends_with_each_product_once_described_by_its_newest_brochure() -> None:
    prompt = system_prompt(CARDS)

    assert prompt.splitlines()[-3:] == [
        "- CellStation (flotation control): Controls levels. Brochures: `cellstation` (2023).",
        "- Larox PF (pressure filter): Newer words. "
        "Brochures: `larox-pf-brochure-b` (2024), `larox-pf-brochure-a` (2021).",
        "- Undated filter (filter): Filters. Brochures: `undated` (no year).",
    ]
    assert "Older words." not in prompt
