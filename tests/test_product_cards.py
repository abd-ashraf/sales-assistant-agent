"""Tests for the product cards the model writes at ingest."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from sales_assistant.brochures import BrochureError, Page
from sales_assistant.product_cards import (
    BROCHURE_TEXT_LIMIT,
    CARDS_FILE,
    ProductCard,
    ProductDescription,
    description_request,
    load_cards,
    save_cards,
    write_cards,
)

REAL_CARDS = Path(__file__).parents[1] / ".cache" / CARDS_FILE

PAGES = [
    Page("larox-pf-brochure-a", 1, 2021, "Larox PF filter"),
    Page("larox-pf-brochure-a", 2, 2021, "Technical specifications"),
    Page("larox-pf-brochure-b", 1, 2024, "Larox PF filter, new edition"),
]
LAROX_PF = ProductDescription(product="Larox PF", category="pressure filter", summary="Filters.")


def test_write_cards_writes_one_card_per_brochure_with_its_year() -> None:
    cards = write_cards(PAGES, Mock(return_value=LAROX_PF))

    assert cards == [
        ProductCard("larox-pf-brochure-a", 2021, "Larox PF", "pressure filter", "Filters."),
        ProductCard("larox-pf-brochure-b", 2024, "Larox PF", "pressure filter", "Filters."),
    ]


def test_write_cards_sends_each_brochure_its_own_text() -> None:
    describe = Mock(return_value=LAROX_PF)

    write_cards(PAGES, describe)

    first, second = (call.args[0] for call in describe.call_args_list)
    assert "Larox PF filter\nTechnical specifications" in first
    assert "new edition" in second
    assert "new edition" not in first


def test_write_cards_keeps_saved_cards_and_describes_only_the_other_brochures() -> None:
    saved = ProductCard("larox-pf-brochure-a", 2021, "Larox PF", "filter", "Saved earlier.")
    removed = ProductCard("old-brochure", 2019, "Old product", "filter", "No longer there.")
    describe = Mock(return_value=LAROX_PF)

    cards = write_cards(PAGES, describe, [saved, removed])

    assert [card.summary for card in cards] == ["Saved earlier.", "Filters."]
    describe.assert_called_once()
    assert "new edition" in describe.call_args.args[0]


def test_description_request_sends_the_brochure_text_up_to_the_limit() -> None:
    pages = [Page("long-brochure", 1, None, "x" * (BROCHURE_TEXT_LIMIT + 1))]

    request = description_request(pages)

    assert "x" * BROCHURE_TEXT_LIMIT in request
    assert "x" * (BROCHURE_TEXT_LIMIT + 1) not in request


def test_load_cards_reads_back_what_save_cards_wrote(tmp_path: Path) -> None:
    cards = [ProductCard("ac-filter", None, "AC filter", "filter", "Removes organics.")]
    save_cards(cards, tmp_path / CARDS_FILE)

    assert load_cards(tmp_path / CARDS_FILE) == cards


def test_load_cards_asks_for_ingest_with_a_key_when_nothing_was_saved(tmp_path: Path) -> None:
    with pytest.raises(BrochureError, match="with OPENAI_API_KEY set"):
        load_cards(tmp_path / CARDS_FILE)


def test_real_cards_name_both_larox_pf_brochures_alike_and_the_pf_ds_apart() -> None:
    if not REAL_CARDS.exists():
        pytest.skip("no product cards yet: run `sales-assistant ingest` with OPENAI_API_KEY set")
    products = {card.brochure: card.product for card in load_cards(REAL_CARDS)}

    assert products["larox-pf-brochure-a"] == products["larox-pf-brochure-b"]
    assert products["larox-pf-ds"] != products["larox-pf-brochure-a"]
