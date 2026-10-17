"""Command-line entry point: `sales-assistant <command>`."""

import io
import sys
from collections.abc import Iterator
from importlib.metadata import version
from itertools import groupby
from typing import Annotated
from uuid import uuid4

import openai
import typer
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import MessagesState
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from sales_assistant.brochures import (
    PAGES_FILE,
    BrochureError,
    Page,
    load_pages,
    read_brochures,
    save_pages,
)
from sales_assistant.config import BROCHURES_DIR, CACHE_DIR, EXPECTED_DATA, Settings, load_settings
from sales_assistant.graph import MAX_GRAPH_STEPS, Agent, build_agent
from sales_assistant.llm import chat_model
from sales_assistant.product_cards import (
    CARDS_FILE,
    ProductCard,
    describe_with,
    load_cards,
    save_cards,
    write_cards,
)
from sales_assistant.prompts import system_prompt
from sales_assistant.search import PageIndex, best_line
from sales_assistant.tools import make_search_tool

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
def ingest(
    rewrite_cards: Annotated[
        bool,
        typer.Option(
            "--rewrite-cards", help="Write every product card again, not only the missing ones."
        ),
    ] = False,
) -> None:
    """Read the brochures into clean pages, then have the model write a card per brochure."""
    settings = load_settings()
    try:
        pages = read_brochures(settings.data_dir / BROCHURES_DIR)
    except BrochureError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error
    pages_path = CACHE_DIR / PAGES_FILE
    save_pages(pages, pages_path)
    cards = _write_product_cards(settings, pages, rewrite_cards) if settings.has_openai_key else []
    products = {card.brochure: card.product for card in cards}

    table = Table("Brochure", "Year", "Pages", "Product")
    for brochure, group in groupby(pages, key=lambda page: page.brochure):
        brochure_pages = list(group)
        table.add_row(
            brochure,
            str(brochure_pages[0].year or "-"),
            str(len(brochure_pages)),
            products.get(brochure, "-"),
        )
    console.print(table)
    console.print(f"{len(pages)} pages saved to {pages_path}")
    if cards:
        console.print(f"{len(cards)} product cards saved to {CACHE_DIR / CARDS_FILE}")
    else:
        console.print("Product cards not written: set OPENAI_API_KEY, then run ingest again.")


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


@app.command()
def ask(question: Annotated[str, typer.Argument(help="The question, in plain words.")]) -> None:
    """Ask one question; see each tool the agent uses, then its answer."""
    agent = _load_agent()
    if not _answer(agent, question, thread_id=uuid4().hex):
        raise typer.Exit(code=1)


@app.command()
def chat() -> None:
    """Talk with the agent; it remembers the conversation until you leave."""
    agent = _load_agent()
    thread_id = uuid4().hex
    console.print("Ask about Metso products. Type exit to leave.")
    while True:
        try:
            question = console.input("[bold]you>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if question.lower() in {"exit", "quit"}:
            break
        if question:
            _answer(agent, question, thread_id)


def _write_product_cards(settings: Settings, pages: list[Page], rewrite: bool) -> list[ProductCard]:
    """Have the model write a card for each brochure without one, and save all the cards."""
    cards_path = CACHE_DIR / CARDS_FILE
    existing = [] if rewrite or not cards_path.exists() else load_cards(cards_path)
    try:
        with console.status("Writing product cards..."):
            cards = write_cards(pages, describe_with(chat_model(settings)), existing)
    except openai.APIError as error:
        _print_api_error(error)
        raise typer.Exit(code=1) from error
    save_cards(cards, cards_path)
    return cards


def _load_agent() -> Agent:
    """Build the agent from the prepared pages and cards, or exit saying what is missing."""
    settings = load_settings()
    if not settings.has_openai_key:
        console.print("[red]OPENAI_API_KEY is not set:[/] add it to .env (see .env.example).")
        raise typer.Exit(code=1)
    try:
        pages = load_pages(CACHE_DIR / PAGES_FILE)
        cards = load_cards(CACHE_DIR / CARDS_FILE)
    except BrochureError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error
    tools = [make_search_tool(PageIndex(pages))]
    return build_agent(chat_model(settings), tools, system_prompt(cards), InMemorySaver())


def _answer(agent: Agent, question: str, thread_id: str) -> bool:
    """Run one turn: print each tool call and what it found, then the answer.

    Returns False if the turn stopped without an answer.
    """
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": MAX_GRAPH_STEPS,
    }
    replies: list[AIMessage] = []
    try:
        with console.status("Thinking..."):
            for message in _new_messages(agent, question, config):
                _print_step(message)
                if isinstance(message, AIMessage):
                    replies.append(message)
    except GraphRecursionError:
        console.print(f"[red]Stopped after {MAX_GRAPH_STEPS} steps without an answer.[/]")
        return False
    except openai.APIError as error:
        _print_api_error(error)
        return False

    console.print()
    console.print(Markdown(replies[-1].text))
    tokens = sum(reply.usage_metadata["total_tokens"] for reply in replies if reply.usage_metadata)
    console.print(Text(f"model calls: {len(replies)} · tokens: {tokens:,}", style="dim"))
    console.print()
    return True


def _new_messages(agent: Agent, question: str, config: RunnableConfig) -> Iterator[BaseMessage]:
    """Yield the messages each graph step adds to the conversation, as the step ends."""
    turn: MessagesState = {"messages": [HumanMessage(question)]}
    for update in agent.stream(turn, config, stream_mode="updates"):
        for step in update.values():
            yield from step["messages"]


def _print_step(message: BaseMessage) -> None:
    """Print the tool calls the model asked for, or what a tool found, as dim lines."""
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            arguments = ", ".join(f"{name}={value!r}" for name, value in call["args"].items())
            console.print(Text(f"  → {call['name']}({arguments})", style="dim"))
    elif isinstance(message, ToolMessage):
        found = ", ".join(message.artifact or []) or message.text
        console.print(Text(f"    ← {found}", style="dim"))


def _print_api_error(error: openai.APIError) -> None:
    console.print(Text(f"OpenAI request failed: {error.message}", style="red"))
