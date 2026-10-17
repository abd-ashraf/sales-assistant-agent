"""The agent's tools. Their descriptions are prompts: the model reads them to pick a tool."""

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from sales_assistant.search import PageIndex, SearchHit

SEARCH_DESCRIPTION = (
    "Search Metso's product brochures by keyword. Returns the best-matching pages, each "
    "headed by its citation and the brochure's year. Use it for any question about a "
    "product: what it does, its specifications and options, or whether it fits a "
    "customer's problem. Product names, model codes and the words a brochure would use "
    "work best. The brochures list no prices."
)


class SearchInput(BaseModel):
    """The arguments of search_product_docs."""

    query: str = Field(description="Keywords to look for, such as 'cake washing options'.")
    brochures: list[str] | None = Field(
        default=None,
        description="Brochure names from the product list to search within; leave out to "
        "search all brochures.",
    )


def make_search_tool(index: PageIndex) -> BaseTool:
    """Return the search_product_docs tool, which searches `index`."""

    # The second value returned, the pages' citations, is kept from the model; the CLI shows it.
    @tool(
        "search_product_docs",
        description=SEARCH_DESCRIPTION,
        args_schema=SearchInput,
        response_format="content_and_artifact",
    )
    def search_product_docs(
        query: str, brochures: list[str] | None = None
    ) -> tuple[str, list[str]]:
        """Return the best-matching pages as text, and their citations."""
        unknown = sorted(set(brochures or ()) - index.brochures)
        if unknown:
            known = ", ".join(sorted(index.brochures))
            return f"Unknown brochure: {', '.join(unknown)}. Known brochures: {known}.", []
        hits = index.search(query, brochures=brochures)
        if not hits:
            return "No page shares a word with this query.", []
        pages = "\n\n".join(f"[{_citation(hit)}]{_year(hit)}\n{hit.page.text}" for hit in hits)
        return pages, [_citation(hit) for hit in hits]

    return search_product_docs


def _citation(hit: SearchHit) -> str:
    return f"{hit.page.brochure} p.{hit.page.page_number}"


def _year(hit: SearchHit) -> str:
    return f" ({hit.page.year})" if hit.page.year else ""
