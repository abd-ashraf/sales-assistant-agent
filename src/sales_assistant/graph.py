"""The agent: a LangGraph graph that loops between the model and its tools."""

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Checkpointer

# Graph steps per question: each model call and each round of tool calls is one, so 12 allow
# five rounds of tools and an answer. Even, so a turn stopped here still ends on tool results.
MAX_GRAPH_STEPS = 12

Agent = CompiledStateGraph[MessagesState]


def build_agent(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    checkpointer: Checkpointer = None,
) -> Agent:
    """Return the agent graph: the model step answers or asks for tools, the tool step runs them.

    With a `checkpointer`, the graph keeps each conversation by its thread ID.
    """
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState) -> MessagesState:
        """Send the system prompt and the conversation; the reply is an answer or tool calls."""
        reply = model_with_tools.invoke([SystemMessage(system_prompt), *state["messages"]])
        return {"messages": [reply]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_node("run_tools", ToolNode(tools))
    graph.add_edge(START, "call_model")
    graph.add_conditional_edges("call_model", route_after_model, ["run_tools", END])
    graph.add_edge("run_tools", "call_model")
    return graph.compile(checkpointer=checkpointer)


def route_after_model(state: MessagesState) -> str:
    """Go to the tool step if the model asked for tools; otherwise the turn is over."""
    reply = state["messages"][-1]
    return "run_tools" if isinstance(reply, AIMessage) and reply.tool_calls else END
