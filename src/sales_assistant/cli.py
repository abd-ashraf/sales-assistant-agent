"""Command-line entry point: `sales-assistant <command>`."""

import io
import sys
from importlib.metadata import version
from itertools import groupby
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from sales_assistant.brochures import (
    PAGES_FILE,
    BrochureError,
    load_pages,
    read_brochures,
    save_pages,
)
from sales_assistant.config import BROCHURES_DIR, CACHE_DIR, EXPECTED_DATA, load_settings
from sales_assistant.search import PageIndex, best_line

APP_HELP = "Sales assistant for Metso field sales: products, service costs, flotation data."

app = typer.Typer(help=APP_HELP, no_args_is_help=True, add_completion=False)
console = Console()


def use_utf8_output() -> None:
    """Write output as UTF-8: on Windows, a redirect would use a code page that lacks "μ"."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def run() -> None:
    """Run the `sales-assistant` command."""
    use_utf8_output()
    app()


def _print_version(show: bool) -> None:
    if show:
        console.print(f"sales-assistant {version('sales-assistant')}")
        raise typer.Exit


@app.callback()
def main(
    _show_version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """Sales assistant for Metso field sales: products, service costs, flotation data."""


@app.command()
def check() -> None:
    """Check the setup: the data folder's contents and whether the OpenAI key is set."""
    settings = load_settings()
    missing = [name for name in EXPECTED_DATA if not (settings.data_dir / name).exists()]

    console.print(f"Data folder: {settings.data_dir.resolve()}")
    for name in EXPECTED_DATA:
        status = "[red]missing[/]" if name in missing else "[green]ok[/]"
        console.print(f"  {status}  {name}")

    key_status = "[green]set[/]" if settings.has_openai_key else "[red]not set[/]"
    console.print(f"OpenAI key: {key_status} (OPENAI_API_KEY; not tested against the API)")
    console.print(f"Model: {settings.openai_model} (OPENAI_MODEL; not tested)")

    if missing or not settings.has_openai_key:
        raise typer.Exit(code=1)


@app.command()
def ingest() -> None:
    """Read the brochures into clean pages and save them in the cache folder."""
    settings = load_settings()
    try:
        pages = read_brochures(settings.data_dir / BROCHURES_DIR)
    except BrochureError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error
    pages_path = CACHE_DIR / PAGES_FILE
    save_pages(pages, pages_path)

    table = Table("Brochure", "Year", "Pages")
    for brochure, group in groupby(pages, key=lambda page: page.brochure):
        brochure_pages = list(group)
        table.add_row(brochure, str(brochure_pages[0].year or "-"), str(len(brochure_pages)))
    console.print(table)
    console.print(f"{len(pages)} pages saved to {pages_path}")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="What to look for, in plain words.")],
    brochures: Annotated[
        list[str] | None,
        typer.Option(
            "--brochure", "-b", help="Only this brochure (file name without .pdf); repeatable."
        ),
    ] = None,
) -> None:
    """Show the brochure pages that best match a query, as the agent's search will see them."""
    try:
        index = PageIndex(load_pages(CACHE_DIR / PAGES_FILE))
    except BrochureError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error
    unknown = sorted(set(brochures or ()) - index.brochures)
    if unknown:
        known = ", ".join(sorted(index.brochures))
        console.print(f"[red]Unknown brochure: {', '.join(unknown)}[/]. Known: {known}")
        raise typer.Exit(code=1)

    hits = index.search(query, brochures=brochures)
    if not hits:
        console.print("No page shares a word with the query.")
        return
    table = Table("#", "Page", "Score", "Best-matching line")
    for rank, hit in enumerate(hits, start=1):
        page = hit.page
        table.add_row(
            str(rank),
            f"{page.brochure} p.{page.page_number}",
            f"{hit.score:.1f}",
            best_line(page.text, query),
        )
    console.print(table)
