"""Optional tracing in Langfuse: with its settings present, each agent turn becomes a trace."""

import httpx
from langchain_core.runnables import RunnableConfig
from langfuse import get_client
from langfuse.api.core import ApiError
from langfuse.langchain import CallbackHandler

from sales_assistant.config import Settings


def tracing_config(settings: Settings, session_id: str, trace_name: str) -> RunnableConfig:
    """Return run settings that send a turn to Langfuse, or none when tracing is off."""
    if settings.langfuse_url is None:
        return {}
    return {
        "callbacks": [CallbackHandler()],
        # Langfuse groups a chat's turns into one session, and names each trace.
        "metadata": {"langfuse_session_id": session_id, "langfuse_trace_name": trace_name},
    }


def langfuse_problem() -> str | None:
    """Ask Langfuse whether it accepts the keys; return what is wrong, or None."""
    try:
        accepted = get_client().auth_check()
    except httpx.HTTPError:
        return "not reachable"
    except ApiError:
        return "keys rejected"
    return None if accepted else "client not set up"
