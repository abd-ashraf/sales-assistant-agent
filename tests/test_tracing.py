"""Tests for the optional tracing in Langfuse, without a Langfuse server."""

from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from langfuse.api.core import ApiError
from langfuse.langchain import CallbackHandler

from sales_assistant import tracing
from sales_assistant.config import Settings
from sales_assistant.tracing import langfuse_problem, tracing_config

LANGFUSE_URL = "http://localhost:3000"


def make_settings(langfuse_url: str | None) -> Settings:
    """Settings that differ only in whether Langfuse is set up."""
    return Settings(Path("data"), "gpt-6-luna", has_openai_key=True, langfuse_url=langfuse_url)


def test_tracing_config_is_empty_when_langfuse_is_not_set_up() -> None:
    assert not tracing_config(make_settings(None), session_id="chat-1", trace_name="chat")


def test_tracing_config_adds_the_langfuse_callback_and_names_the_session_and_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", LANGFUSE_URL)

    config = tracing_config(make_settings(LANGFUSE_URL), session_id="chat-1", trace_name="chat")

    callbacks = config.get("callbacks")
    assert isinstance(callbacks, list)
    assert [type(callback) for callback in callbacks] == [CallbackHandler]
    assert config.get("metadata") == {
        "langfuse_session_id": "chat-1",
        "langfuse_trace_name": "chat",
    }


@pytest.mark.parametrize(
    ("error", "problem"),
    [
        (httpx.ConnectError("connection refused"), "not reachable"),
        (ApiError(status_code=401, body="Unauthorized"), "keys rejected"),
    ],
)
def test_langfuse_problem_says_what_went_wrong(
    monkeypatch: pytest.MonkeyPatch, error: Exception, problem: str
) -> None:
    monkeypatch.setattr(tracing, "get_client", lambda: Mock(auth_check=Mock(side_effect=error)))

    assert langfuse_problem() == problem


@pytest.mark.parametrize(("accepted", "problem"), [(True, None), (False, "client not set up")])
def test_langfuse_problem_follows_the_auth_check(
    monkeypatch: pytest.MonkeyPatch, accepted: bool, problem: str | None
) -> None:
    monkeypatch.setattr(tracing, "get_client", lambda: Mock(auth_check=Mock(return_value=accepted)))

    assert langfuse_problem() == problem
