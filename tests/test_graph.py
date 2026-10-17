"""Tests for the agent graph, with a scripted model in place of the API."""

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END

from sales_assistant.brochures import Page
from sales_assistant.graph import MAX_GRAPH_STEPS, Agent, build_agent, route_after_model
from sales_assistant.search import PageIndex
from sales_assistant.tools import make_search_tool
from tests.fakes import ScriptedChatModel, never_answering_model, scripted_model, tool_call

PAGES = [
    Page("larox-pf-ds", 2, 2025, "Chambers 8 10 12"),
    Page("cellstation", 1, 2023, "Pulp level control in flotation cells"),
]
SYSTEM_PROMPT = "Answer from the brochures."
CONFIG: RunnableConfig = {
    "configurable": {"thread_id": "chat-1"},
    "recursion_limit": MAX_GRAPH_STEPS,
}


def make_agent(model: ScriptedChatModel) -> Agent:
    """An agent that searches two pages and keeps its conversations in memory."""
    return build_agent(model, [make_search_tool(PageIndex(PAGES))], SYSTEM_PROMPT, InMemorySaver())


def ask(agent: Agent, question: str) -> list[BaseMessage]:
    """Run one turn of the chat in CONFIG, and return the whole conversation so far."""
    messages: list[BaseMessage] = agent.invoke({"messages": [HumanMessage(question)]}, CONFIG)[
        "messages"
    ]
    return messages


@pytest.mark.parametrize(
    ("reply", "next_step"),
    [(tool_call("search_product_docs", query="chambers"), "run_tools"), (AIMessage("Hi."), END)],
)
def test_route_after_model_runs_tools_only_when_the_model_asked_for_them(
    reply: AIMessage, next_step: str
) -> None:
    assert route_after_model({"messages": [HumanMessage("Hello"), reply]}) == next_step


def test_a_reply_without_tool_calls_ends_the_turn() -> None:
    messages = ask(make_agent(scripted_model("Which filter model do you have?")), "Help me")

    assert [type(message) for message in messages] == [HumanMessage, AIMessage]


def test_a_tool_call_runs_the_search_and_the_model_answers_from_its_pages() -> None:
    model = scripted_model(tool_call("search_product_docs", query="chambers"), "8 to 12.")

    messages = ask(make_agent(model), "How many chambers can a PF-DS have?")

    assert [type(message) for message in messages] == [
        HumanMessage,
        AIMessage,
        ToolMessage,
        AIMessage,
    ]
    assert messages[2].text.startswith("[larox-pf-ds p.2] (2025)\nChambers 8 10 12")
    assert model.received[1][-1] == messages[2]


def test_every_model_call_starts_with_the_system_prompt() -> None:
    model = scripted_model(tool_call("search_product_docs", query="chambers"), "8 to 12.")

    ask(make_agent(model), "How many chambers?")

    assert [call[0] for call in model.received] == [SystemMessage(SYSTEM_PROMPT)] * 2


def test_the_chat_keeps_the_conversation_between_turns() -> None:
    agent = make_agent(scripted_model("First answer.", "Second answer."))

    ask(agent, "First question")
    messages = ask(agent, "Second question")

    assert [message.text for message in messages] == [
        "First question",
        "First answer.",
        "Second question",
        "Second answer.",
    ]


def test_the_step_cap_stops_a_model_that_never_answers_and_the_chat_can_go_on() -> None:
    model = never_answering_model("search_product_docs", query="chambers")
    agent = make_agent(model)

    with pytest.raises(GraphRecursionError):
        ask(agent, "How many chambers?")

    assert len(model.received) == MAX_GRAPH_STEPS // 2
    saved = agent.get_state(CONFIG).values["messages"]
    assert isinstance(saved[-1], ToolMessage)
