"""Product cards: what each brochure is about, written once by the model at ingest.

The agent reads the cards in its system prompt, so it knows which products exist, under
which names, and which brochures to search for each.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from sales_assistant.brochures import BrochureError, Page

CARDS_FILE = "product_cards.json"
# The opening pages name and introduce the product, so the rest of a long brochure is left out.
BROCHURE_TEXT_LIMIT = 6000


class ProductDescription(BaseModel):
    """The model's description of the product a brochure is about."""

    # Copied from the title, so the editions of one brochure share a name and are grouped.
    product: str = Field(
        description="The product's name as the brochure's title prints it, without ®, ™ or "
        "the company name."
    )
    category: str = Field(description="What kind of equipment or service it is, in a few words.")
    summary: str = Field(description="One sentence: what it does and which problems it solves.")


@dataclass(frozen=True)
class ProductCard:
    """One brochure's product, as the agent sees it in its system prompt."""

    brochure: str
    year: int | None
    product: str
    category: str
    summary: str


DescribeBrochure = Callable[[str], ProductDescription]


def description_request(pages: list[Page]) -> str:
    """Return the request for one brochure's description, with the brochure's opening text."""
    text = "\n".join(page.text for page in pages)[:BROCHURE_TEXT_LIMIT]
    return (
        "Describe the product this Metso brochure is about, using only its text.\n\n"
        f"Brochure text:\n{text}"
    )


def write_cards(
    pages: list[Page], describe: DescribeBrochure, existing: list[ProductCard] | None = None
) -> list[ProductCard]:
    """Return one card per brochure: existing cards are kept, the other brochures described."""
    pages_by_brochure: dict[str, list[Page]] = {}
    for page in pages:
        pages_by_brochure.setdefault(page.brochure, []).append(page)
    saved = {card.brochure: card for card in existing or []}
    return [
        saved[brochure] if brochure in saved else _write_card(brochure, brochure_pages, describe)
        for brochure, brochure_pages in pages_by_brochure.items()
    ]


def _write_card(brochure: str, pages: list[Page], describe: DescribeBrochure) -> ProductCard:
    """Have the model describe one brochure, and return its card."""
    description = describe(description_request(pages))
    return ProductCard(
        brochure=brochure,
        year=pages[0].year,
        product=description.product,
        category=description.category,
        summary=description.summary,
    )


def save_cards(cards: list[ProductCard], path: Path) -> None:
    """Write the cards to `path` as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([asdict(card) for card in cards], ensure_ascii=False, indent=2)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def load_cards(path: Path) -> list[ProductCard]:
    """Read the cards that `save_cards` wrote to `path`."""
    if not path.exists():
        raise BrochureError(
            f"No product cards at {path}: run `sales-assistant ingest` with OPENAI_API_KEY set"
        )
    return [ProductCard(**card) for card in json.loads(path.read_text(encoding="utf-8"))]
