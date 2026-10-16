"""Command-line entry point: `sales-assistant <command>`."""

from importlib.metadata import version
from typing import Annotated

import typer
from rich.console import Console

from sales_assistant.config import EXPECTED_DATA, load_settings

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
