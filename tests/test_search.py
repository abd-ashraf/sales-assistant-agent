"""Tests for keyword search over brochure pages."""

from pathlib import Path

import pytest

from sales_assistant.brochures import Page, read_brochures
from sales_assistant.search import PageIndex, best_line, tokenize

REAL_BROCHURES = Path(__file__).parents[1] / "data" / "brochures"


def make_page(brochure: str, text: str, page_number: int = 1) -> Page:
    """A page with no year, for search tests."""
    return Page(brochure=brochure, page_number=page_number, year=None, text=text)


PAGES = [
    make_page("larox-pf-ds", "Larox PF-DS tower press\nfilter cloth and filter plates"),
    make_page("cellstation", "CellStation flotation level control\nfroth stability"),
    make_page("filter-optimizer", "Filter optimizer: filter cycles under changing slurry"),
]


def answers(brochure: str, *page_numbers: int) -> set[tuple[str, int]]:
    """The (brochure, page number) pairs that answer a question."""
    return {(brochure, number) for number in page_numbers}


# Questions as the agent might word them, and the pages that answer them.
QUESTIONS = [
    ("filter performance changing slurry characteristics", answers("filter-optimizer", 2)),
    ("weight of a tower press with 14 chambers", answers("larox-pf-ds", 5)),
    ("pulp level control in flotation cells", answers("cellstation", 1, 2)),
    ("sparger options Microcel SonicSparger", answers("columncell", 2, 3)),
    ("recovery of fine and ultra-fine particles", answers("concorde-cell", 2, 6, 7)),
    ("mill discharge pump sizes", answers("md-series-pump", 1, 2)),
    ("remove insoluble organics with coalescing media", answers("gm-filter", 1)),
    ("upgrade the rotor and stator mixing mechanism", answers("floatforce-upgrade", 1, 3)),
    ("shaft sealing options for slurry pumps", answers("orion-series-pump", 5, 6, 7)),
    (
        "cloth changeover takes 30 minutes",
        answers("larox-pf-brochure-a", 2) | answers("larox-pf-brochure-b", 4),
    ),
    ("maximum operating pressure of the PF-DS", answers("larox-pf-ds", 2, 3, 5)),
    (
        "number of filter plates in a PF 60",
        answers("larox-pf-brochure-a", 5) | answers("larox-pf-brochure-b", 7, 8),
    ),
    ("what the Filter optimizer delivery includes", answers("filter-optimizer", 3)),
    ("ExactLevel controller", answers("cellstation", 1, 2)),
    ("AC filter vessel diameter and service flow", answers("ac-filter", 2)),
    ("SonicSparger Jet inlet air pressure", answers("columncell", 3)),
    ("Concorde Cell blast tube capacity", answers("concorde-cell", 4)),
    ("FloatForce rotor and stator features", answers("floatforce-upgrade", 3)),
    ("MD pump service life in hours", answers("md-series-pump", 1)),
    ("Bucim copper mine power savings", answers("md-series-pump", 3)),
    ("Orion pump materials of construction", answers("orion-series-pump", 5)),
    ("cake washing options", answers("larox-pf-ds", 2, 3)),
    ("FDA compliance for food grade", answers("larox-pf-ds", 2, 4)),
    ("battery metals solvent extraction", answers("ac-filter", 1) | answers("gm-filter", 1)),
]
# Questions in a salesperson's own words; the first is demo prompt 1 from the brief.
OWN_WORDS = [
    (
        "We have Larox pressure filters but performance drops whenever our feed grade changes",
        answers("filter-optimizer", 2),
    ),
    (
        "customer loses fine particles to tailings in flotation",
        answers("concorde-cell", 2, 6, 7, 8),
    ),
    (
        "our flotation cells keep losing level control and the froth is unstable",
        answers("cellstation", 1),
    ),
]


@pytest.fixture(name="real_index", scope="module")
def fixture_real_index() -> PageIndex:
    """An index over the real brochures; the tests using it skip when the data is absent."""
    if not REAL_BROCHURES.exists():
        pytest.skip("the assignment data is not in this checkout")
    return PageIndex(read_brochures(REAL_BROCHURES))


def test_tokenize_lowercases_splits_hyphens_and_keeps_decimals_whole() -> None:
    words = tokenize("ColumnCell™ and Larox® PF-DS: 16 bar, 1.35 t/m3")

    assert words == ["columncell", "and", "larox", "pf", "ds", "16", "bar", "1.35", "t", "m3"]


def test_search_ranks_a_page_with_a_rare_word_above_pages_repeating_a_common_one() -> None:
    hits = PageIndex(PAGES).search("filter froth")

    assert [hit.page.brochure for hit in hits] == ["cellstation", "filter-optimizer", "larox-pf-ds"]


def test_search_leaves_out_pages_without_a_shared_word() -> None:
    hits = PageIndex(PAGES).search("froth")

    assert [hit.page.brochure for hit in hits] == ["cellstation"]


def test_search_finds_a_code_written_without_its_hyphen() -> None:
    assert PageIndex(PAGES).search("PF DS")[0].page.brochure == "larox-pf-ds"


def test_search_can_be_limited_to_some_brochures() -> None:
    hits = PageIndex(PAGES).search("filter", brochures={"larox-pf-ds"})

    assert [hit.page.brochure for hit in hits] == ["larox-pf-ds"]


def test_search_returns_at_most_top_k_pages() -> None:
    assert len(PageIndex(PAGES).search("filter", top_k=1)) == 1


def test_best_line_picks_the_line_sharing_the_most_words() -> None:
    text = "Larox PF-DS tower press\nfilter cloth and filter plates"

    assert best_line(text, "filter plates") == "filter cloth and filter plates"


def test_real_search_finds_the_answer_page_in_the_top_5_for_22_of_24_questions(
    real_index: PageIndex,
) -> None:
    found = [
        question
        for question, pages in QUESTIONS
        if any(
            (hit.page.brochure, hit.page.page_number) in pages
            for hit in real_index.search(question)
        )
    ]

    assert len(found) >= 22


@pytest.mark.parametrize(("question", "pages"), OWN_WORDS)
def test_real_search_ranks_an_answer_page_first_for_a_salespersons_own_words(
    real_index: PageIndex, question: str, pages: set[tuple[str, int]]
) -> None:
    best = real_index.search(question)[0].page

    assert (best.brochure, best.page_number) in pages


def test_real_search_within_one_brochure_finds_its_spec_table(real_index: PageIndex) -> None:
    hits = real_index.search("weight of a tower press with 14 chambers", brochures={"larox-pf-ds"})

    assert ("larox-pf-ds", 5) in [(hit.page.brochure, hit.page.page_number) for hit in hits]
