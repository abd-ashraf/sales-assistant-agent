"""Tests for reading the settings."""

import pytest

from sales_assistant.config import load_settings


@pytest.mark.usefixtures("workdir")
def test_tracing_is_on_only_when_all_three_langfuse_settings_are_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    two_of_three = load_settings()
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    assert two_of_three.langfuse_url is None
    assert load_settings().langfuse_url == "http://localhost:3000"
