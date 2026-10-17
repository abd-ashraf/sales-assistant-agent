# Metso sales assistant agent

A command-line assistant for a Metso salesperson on a call with a mining customer. For each
message it decides for itself whether to answer, ask one short question, or use a tool, and
it says so when the answer is not in its data.

- **Products:** answers questions and recommends a product, from the brochures only.
- **Service costs:** estimates a field service visit, from past service reports only.
- **Flotation (optional part):** judges concentrate readings against plant history.

![How the assistant fits together](docs/diagrams/overview.drawio.svg)

## What works so far

- Project skeleton: installs, lints and tests; `check` verifies the setup.
- Brochures read page by page with `ingest`: 73 clean pages, each tagged with its
  brochure, page and year. The PDF reader was picked by comparing six
  ([measurements](docs/TRACKER.md#measurements)).
- Keyword search over the pages with `search`: best pages first, optionally within named
  brochures. 22 of 24 test questions find their answer page in the top 5.
- Product questions answered by a LangGraph agent with `ask` or `chat`: it searches the
  brochures, cites the pages it used, and says when they do not cover a question. At
  `ingest`, the model also writes a short card per brochure, so the agent knows which
  products exist.

The full plan, ticked off step by step: [docs/TRACKER.md](docs/TRACKER.md).

## How the agent works

![The agent graph](docs/diagrams/agent.drawio.svg)

Each question runs a two-step loop. `call_model` sends the model the system prompt (rules
and the product cards), the conversation so far and the tool descriptions; the model
answers, asks a question, or requests tools. The routing rule, `route_after_model`, sends
tool requests to `run_tools` and otherwise ends the turn; tool results go back to the
model. The CLI prints every tool call, so each routing decision is visible.

## Quick start

Needs [uv](https://docs.astral.sh/uv/), which also installs the right Python version.
Copy the assignment's `data/` folder into the repository root first (it is not part of the
repository), or point `DATA_DIR` in `.env` at it.

```bash
uv sync
cp .env.example .env              # then add your OPENAI_API_KEY
uv run sales-assistant check      # checks the data folder and the key
uv run sales-assistant ingest     # reads the brochures and writes product cards into .cache/
uv run sales-assistant search "filter performance when the feed changes"
uv run sales-assistant ask "We have Larox pressure filters but performance drops whenever our feed grade changes"
uv run sales-assistant chat       # a conversation; type exit to leave
```

## Development

```bash
uv run ruff check                 # lint
uv run pylint src tests           # deeper lint
uv run ruff format --check        # formatting
uv run mypy                       # types
uv run pytest                     # tests
```

The same checks run on every push, in GitHub Actions.
