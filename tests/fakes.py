"""A scripted chat model, so the agent can be tested without calling the API."""

from collections.abc import Callable, Sequence
from itertools import count
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

_call_ids = count(1)


class ScriptedChatModel(GenericFakeChatModel):
    """Replies with scripted messages in turn, and keeps the messages each call was sent."""

    received: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Ignore the tools: the replies are scripted."""
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)


def scripted_model(*replies: AIMessage | str) -> ScriptedChatModel:
    """A model that replies with `replies` in turn: text answers, or messages asking for tools."""
    return ScriptedChatModel(messages=iter(replies))


def never_answering_model(tool_name: str, **args: Any) -> ScriptedChatModel:
    """A model that asks for the same tool call every time and never answers."""
    # A new message each time: the graph would replace, not add, a message it already holds.
    return ScriptedChatModel(messages=(tool_call(tool_name, **args) for _ in count()))


def tool_call(name: str, **args: Any) -> AIMessage:
    """A model reply that asks for one tool call."""
    call_id = f"call_{next(_call_ids)}"
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])
