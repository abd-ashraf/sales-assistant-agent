"""Command-line entry point: `sales-assistant <command>`."""

from importlib.metadata import version
from itertools import groupby
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from sales_assistant.brochures import PAGES_FILE, BrochureError, read_brochures, save_pages
from sales_assistant.config import BROCHURES_DIR, CACHE_DIR, EXPECTED_DATA, load_settings

APP_HELP = "Sales assistant for Metso field sales: products, service costs, flotation data."

app = typer.Typer(help=APP_HELP, no_args_is_help=True, add_completion=False)
console = Console()


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
